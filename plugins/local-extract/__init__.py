"""local-extract: web_extract backend that fetches pages from this VM (the URL never leaves it) and hands only
the pages it can't handle (blocked requests, PDFs, JavaScript-only pages) to the keyless cloud ring
(Parallel, failing over to Keenable/Tavily/Firecrawl). Enable with web.extract_backend: local-extract."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from plugins.web._common import BaseWebSearchProvider, document, keyless_extract, page_error, run_extract_async

from . import extractor

logger = logging.getLogger(__name__)


class LocalExtractProvider(BaseWebSearchProvider):
    NAME = "local-extract"
    DISPLAY_NAME = "Local extract (cloud fallback)"
    KEY_ENV = ""
    EXTRACT = True
    KEYLESS = False

    def is_available(self) -> bool:
        return True

    def supports_search(self) -> bool:
        return False

    async def extract(self, urls: list[str], **kwargs: Any) -> list[dict[str, Any]]:
        from tools.url_safety import create_ssrf_safe_client, is_safe_url

        def _fetch(u: str):
            # Hermes's client re-checks the address at connect time, so DNS rebinding can't reach the LAN
            with create_ssrf_safe_client(**extractor.CLIENT_KWARGS) as client:
                return extractor.fetch(u, is_safe_url, client)

        async def _body() -> list[dict[str, Any]]:
            local = await asyncio.gather(*(asyncio.to_thread(_fetch, u) for u in urls))
            results: dict[str, dict[str, Any]] = {}
            for u, r in zip(urls, local):
                if r:
                    results[u] = document(u, r["title"], r["content"], source_url=r["final_url"])
            rest = [u for u in urls if u not in results]
            from hermes_cli.config import get_env_value
            fc_base = (get_env_value("LOCAL_EXTRACT_FIRECRAWL_URL") or "").strip()
            if fc_base and rest:   # a self-hosted Firecrawl on the LAN renders JS pages before anything goes to the cloud
                ok = [u for u in rest if is_safe_url(u)]
                for u, r in zip(ok, await asyncio.gather(*(asyncio.to_thread(extractor.firecrawl, u, fc_base) for u in ok))):
                    if r:
                        results[u] = document(u, r["title"], r["content"], source_url=r["final_url"])
                rest = [u for u in urls if u not in results]
            logger.info("local-extract: %d local or Firecrawl, %d to cloud fallback", len(results), len(rest))
            if rest:
                for r in await asyncio.to_thread(keyless_extract, "Parallel", "parallel", rest, logger):
                    results.setdefault(r.get("url", ""), r)
            return [results.get(u) or page_error(u, "extraction failed locally and in the cloud fallback") for u in urls]

        return await run_extract_async("Local extract", logger, urls, _body)


def register(ctx) -> None:
    ctx.register_web_search_provider(LocalExtractProvider())
