"""SearXNG search via a user-hosted instance (``/search?format=json``).

Search-only — SearXNG aggregates upstream engines but does not fetch URLs.
Env: ``SEARXNG_URL=http://localhost:8080``.

Local vm-a tuning (2026-10-24, see ~/agents/ADMIN-CHANGES.md):
- pins engines/categories so a query only hits the reliable web engines;
- sanitizes the query (single line, no chained boolean operators, <= 12 words);
- dedupes by URL, caps at 8 rows, truncates snippets to 400 chars;
- max 2 concurrent requests per process plus a 400 ms stagger between starts;
- 10 s timeout; timeouts, HTTP errors, bad JSON and empty results never raise.
2026-10-26: engines that answer this IP (google and qwant deny it, brave rate-limits it, bing results are
junk), safe search on, and fallbacks when SearXNG fails or its top results don't contain the query's key
words: Brave Search API (only when the profile has BRAVE_SEARCH_API_KEY, from the sealed brave_search_api_key
via hermes-sealed-env), then Hermes's keyless cloud search (the query leaves the LAN). Logs say which served.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any
from urllib.parse import urlsplit

from plugins.web._common import (BaseWebSearchProvider, http_get_json, keyless_search, provider_env, search_fail, search_ok,
                                 setup_schema, titled_rows)

logger = logging.getLogger(__name__)

ENGINES = "mojeek,yahoo,duckduckgo,startpage,brave,google,qwant"  # bing dropped: it answers, but with unrelated homepages
CATEGORIES = "general"
TIMEOUT_S = 10
MAX_RESULTS = 8
MIN_RELEVANT = 2  # top results that must contain the query's key words, else the answer counts as junk
SNIPPET_MAX = 400
MAX_QUERY_WORDS = 12
MAX_CONCURRENT = 2
STAGGER_S = 0.4

# One gateway process serves every profile, so these limits are shared by all of them.
_slots = threading.BoundedSemaphore(MAX_CONCURRENT)
_stagger_lock = threading.Lock()
_next_start = 0.0

_BOOL_OPS = re.compile(r"(?<!\S)(?:AND|OR|NOT|&&|\|\|)(?!\S)")


def sanitize_query(query: str) -> str:
    """Collapse to one line, drop grouping parens and boolean operators, keep <= 12 words.
    Simple operators (site:, -term, "phrase") are kept."""
    q = re.sub(r"\s+", " ", str(query or "")).strip()
    q = _BOOL_OPS.sub(" ", q.replace("(", " ").replace(")", " "))
    words = q.split()[:MAX_QUERY_WORDS]
    q = " ".join(words)
    if q.count('"') % 2:  # truncation split a quoted phrase
        q = q.replace('"', "")
    return q.strip()


def _url_key(url: str) -> str:
    """Dedup key: ignores scheme, leading www., trailing slash and #fragment."""
    try:
        p = urlsplit(url.strip())
        host = p.netloc.lower().removeprefix("www.")
        return f"{host}{p.path.rstrip('/')}?{p.query}"
    except Exception:
        return url.strip()


def _clean(raw_results: list[Any], limit: int) -> list[dict[str, Any]]:
    """Dedupe by URL (first = highest score wins), keep title/url/content, cap and truncate."""
    rows, seen = [], set()
    for r in raw_results:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or "").strip()
        if not url:
            continue
        key = _url_key(url)
        if key in seen:
            continue
        seen.add(key)
        content = re.sub(r"\s+", " ", str(r.get("content") or "")).strip()
        if len(content) > SNIPPET_MAX:
            content = content[: SNIPPET_MAX - 3].rstrip() + "..."
        rows.append({"title": str(r.get("title") or "").strip(), "url": url, "content": content})
        if len(rows) >= limit:
            break
    return rows


def _wait_turn() -> None:
    """Space request starts at least STAGGER_S apart (called while holding a slot)."""
    global _next_start
    with _stagger_lock:
        now = time.monotonic()
        start = max(now, _next_start)
        _next_start = start + STAGGER_S
    if start > now:
        time.sleep(start - now)


_STOP = {"the", "and", "for", "with", "from", "that", "this", "what", "how", "are", "your", "into", "about", "best", "site"}


def keywords(query: str) -> list[str]:
    """Words a relevant result should mention: operators like site:x dropped, short and common words skipped."""
    q = re.sub(r"\b[a-z]+:\S+", " ", query.lower())
    return [w for w in re.findall(r"[a-z0-9][a-z0-9+#.-]{2,}", q) if w not in _STOP]


def relevant_count(query: str, rows: list[dict[str, Any]]) -> int:
    kw = keywords(query)
    if not kw:
        return len(rows)
    need = 1 if len(kw) == 1 else 2
    return sum(1 for r in rows
               if sum(w in f"{r.get('title', '')} {r.get('content', '')} {r.get('url', '')}".lower() for w in kw) >= need)


def _has_hits(result: dict[str, Any]) -> bool:
    return bool(result.get("success")) and bool((result.get("data") or {}).get("web"))


def _score(r: Any) -> float:
    try:
        return float(r.get("score", 0) or 0)
    except (TypeError, ValueError, AttributeError):
        return 0.0


class SearXNGWebSearchProvider(BaseWebSearchProvider):
    """Search via a user-hosted SearXNG instance."""

    NAME = "searxng-tuned"
    DISPLAY_NAME = "SearXNG (tuned)"
    KEY_ENV = "SEARXNG_URL"

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        try:
            return self._search(query, limit)
        except Exception as exc:  # never crash the agent loop
            logger.warning("SearXNG search failed unexpectedly: %s", exc)
            return search_fail(f"SearXNG search failed: {exc}")

    def _search(self, query: str, limit: int) -> dict[str, Any]:
        base_url = provider_env("SEARXNG_URL").rstrip("/")
        if not base_url:
            return search_fail("SEARXNG_URL is not set")
        q = sanitize_query(query)
        if not q:
            return search_fail("Empty search query")
        if q != str(query or "").strip():
            logger.info("SearXNG query sanitized: %r -> %r", query, q)
        try:
            limit = min(max(int(limit), 1), MAX_RESULTS)
        except (TypeError, ValueError):
            limit = MAX_RESULTS

        params = {"q": q, "format": "json", "engines": ENGINES, "categories": CATEGORIES, "pageno": 1, "safesearch": 1}
        with _slots:
            _wait_turn()
            data, failure = http_get_json(
                "SearXNG", f"{base_url}/search", params=params,
                headers={"Accept": "application/json"}, timeout=TIMEOUT_S, logger=logger,
                reach_target=f"SearXNG at {base_url}",
            )
        if failure is None and not isinstance(data, dict):
            failure = search_fail("SearXNG returned an unexpected response")
        if failure is not None:
            return self._fallback(q, limit, "failed") or failure

        raw_results = data.get("results") or []
        if not isinstance(raw_results, list):
            raw_results = []
        rows = _clean(sorted(raw_results, key=_score, reverse=True), limit)
        if not rows:
            down = data.get("unresponsive_engines") or []
            reasons = ", ".join(f"{e[0]}: {e[1]}" for e in down if isinstance(e, (list, tuple)) and len(e) >= 2)
            logger.warning("SearXNG search '%s': no results (unresponsive: %s)", q, reasons or "none")
            fallback = self._fallback(q, limit, "returned no results")
            if fallback:
                return fallback
            if reasons:
                return search_fail(f"SearXNG returned no results; upstream engines unavailable ({reasons[:300]}). "
                                   "Retry later or rephrase as fewer keywords.")
            return search_ok([])

        relevant = relevant_count(q, rows)
        if relevant < min(MIN_RELEVANT, len(rows)):
            fallback = self._fallback(q, limit, f"had only {relevant}/{len(rows)} relevant results")
            if fallback:
                return fallback
        web_results = titled_rows(rows, "content")
        logger.info("SearXNG search '%s': %d results (from %d raw, limit %d)", q, len(web_results), len(raw_results), limit)
        return search_ok(web_results)

    def _fallback(self, q: str, limit: int, why: str) -> dict[str, Any] | None:
        """Brave Search API when this profile has a key, then the keyless cloud ring; None if neither has hits."""
        if provider_env("BRAVE_SEARCH_API_KEY"):
            try:
                from plugins.web.brave_free.provider import BraveFreeWebSearchProvider
                result = BraveFreeWebSearchProvider().search(q, limit)
            except Exception as exc:
                result = search_fail(str(exc))
            if _has_hits(result):
                logger.info("searxng-tuned: SearXNG %s for %r; served by Brave Search API", why, q)
                return result
            logger.warning("searxng-tuned: Brave Search API fallback failed for %r: %s", q, result.get("error"))
        try:
            result = keyless_search("SearXNG fallback", "parallel", q, limit, logger)
        except Exception as exc:
            result = search_fail(str(exc))
        if _has_hits(result):
            logger.info("searxng-tuned: SearXNG %s for %r; served by keyless cloud search", why, q)
            return result
        logger.warning("searxng-tuned: SearXNG %s for %r and every fallback failed", why, q)
        return None

    def get_setup_schema(self) -> dict[str, Any]:
        return setup_schema(
            "SearXNG", "free · self-hosted", "Free, privacy-respecting metasearch. Point SEARXNG_URL at your instance.",
            "SEARXNG_URL", "SearXNG instance URL (e.g. http://localhost:8080)", "https://searx.space/",
        )


def selftest() -> None:
    assert keywords('site:jobs.ashbyhq.com "Senior" "Backend" engineer') == ["senior", "backend", "engineer"]
    rows = [{"title": "GitHub", "url": "https://github.com/", "content": "Where the world builds software"},
            {"title": "felix: tui file manager in rust", "url": "https://github.com/kyoheiu/felix", "content": ""}]
    assert relevant_count("github file manager rust tui", rows) == 1
    assert relevant_count("rust", rows) == 1 and relevant_count("site:x.com", rows) == 2
    print("searxng-tuned selftest ok")

