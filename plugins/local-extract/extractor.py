"""Fetch a page from this VM and turn its HTML into readable text, with no third party involved.
Returns None whenever the page should go to the cloud fallback instead (blocked request, PDF or other
binary, or a JavaScript-only page with almost no text). Redirects are followed by hand so every hop
passes the same private-address check Hermes applies to the first URL."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Callable, Optional
from urllib.parse import urljoin

MAX_BYTES = 3_000_000
MAX_REDIRECTS = 5
TIMEOUT = 15.0
MIN_TEXT = 400          # less text than this from a big page = probably rendered by JavaScript
BIG_PAGE = 20_000
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0 Safari/537.36")
SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "canvas", "nav", "footer", "aside", "form", "button"}
BLOCK = {"p", "div", "section", "article", "main", "header", "br", "tr", "table", "ul", "ol", "dl", "dt", "dd",
         "blockquote", "pre", "hr", "figure", "figcaption", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
CLIENT_KWARGS = {"timeout": TIMEOUT, "follow_redirects": False,
                 "headers": {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
                             "Accept-Language": "en-US,en;q=0.8"}}


class _Text(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base, self.out, self.title = base, [], ""
        self._skip = 0
        self._in_title = False
        self._href: Optional[str] = None
        self._link_text: list[str] = []
        self._pre = 0
        self._line_start = True  # strip leading spaces of ordinary text at the start of a line

    def _emit(self, s: str, starts_line: bool = False) -> None:
        self.out.append(s)
        self._line_start = starts_line

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "title":
            self._in_title = True
        elif tag in BLOCK:
            self._emit("\n", True)
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self._emit("#" * int(tag[1]) + " ", True)
            elif tag == "li":
                self._emit("- ", True)
            elif tag == "pre":
                self._pre += 1
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            if href and not href.startswith(("javascript:", "#", "mailto:")):
                self._href, self._link_text = urljoin(self.base, href), []

    def handle_endtag(self, tag):
        if tag in SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._href is not None:
            text = " ".join("".join(self._link_text).split())
            if text:
                self._emit(f"[{text}]({self._href})")
            self._href = None
        elif tag in BLOCK and tag != "li":  # a list item's start already opened its line
            if tag == "pre":
                self._pre = max(0, self._pre - 1)
            self._emit("\n", True)

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._skip:
            return
        if self._href is not None:
            self._link_text.append(data)
        elif self._pre:
            self._emit(data)
        else:
            d = re.sub(r"\s+", " ", data)
            if self._line_start:
                d = d.lstrip()
            if d:
                self._emit(d)


def html_to_text(page: str, base: str) -> tuple[str, str]:
    """(title, text) of an HTML page."""
    p = _Text(base)
    p.feed(page)
    p.close()
    text = "".join(p.out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
    return " ".join(html.unescape(p.title).split()), text


def fetch(url: str, is_safe: Callable[[str], bool], client=None) -> Optional[dict]:
    """{'url', 'final_url', 'title', 'content'} or None when the cloud fallback should try."""
    import httpx
    own = client is None
    client = client or httpx.Client(**CLIENT_KWARGS)
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            if not is_safe(current):
                return None
            with client.stream("GET", current) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    current = urljoin(current, r.headers["location"])
                    continue
                if r.status_code >= 400:
                    return None
                ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype not in ("text/html", "application/xhtml+xml", "text/plain", "", "application/json", "text/markdown"):
                    return None  # PDFs, images, archives: leave to the cloud fallback
                body = b""
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        break
                raw = body.decode(r.encoding or "utf-8", errors="replace")
            if ctype in ("text/plain", "application/json", "text/markdown"):
                return {"url": url, "final_url": current, "title": "", "content": raw.strip()}
            title, text = html_to_text(raw, current)
            if len(text) < MIN_TEXT and len(raw) > BIG_PAGE:
                return None  # a JavaScript app shell: the cloud renderer does better
            return {"url": url, "final_url": current, "title": title, "content": text}
        return None  # too many redirects
    except (httpx.HTTPError, OSError, ValueError):
        return None
    finally:
        if own:
            client.close()


def selftest() -> None:
    page = ("<html><head><title> Test &amp; Page </title><script>var x=1;</script></head><body><nav>Menu</nav>"
            "<main><h1>Hello</h1><p>First   paragraph with <a href='/next'>a link</a>.</p><ul><li>One</li><li>Two</li></ul>"
            "<pre>  code   kept\n  as is</pre></main><footer>Copyright</footer></body></html>")
    title, text = html_to_text(page, "https://example.com/a/")
    assert title == "Test & Page", title
    assert "# Hello" in text and "[a link](https://example.com/next)" in text, text
    assert "- One" in text and "Menu" not in text and "Copyright" not in text and "var x" not in text, text
    assert "  code   kept" in text, text

    import httpx

    def handler(req):
        path = req.url.path
        if path == "/redir":
            return httpx.Response(302, headers={"location": "http://10.0.0.16/"})
        if path == "/pdf":
            return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")
        if path == "/blocked":
            return httpx.Response(403, text="no bots")
        if path == "/spa":
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<div id=root></div>" + "<script>x</script>" * 3000)
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=page)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    safe = lambda u: "10.0.0." not in u  # stands in for Hermes's private-address check
    assert fetch("https://example.com/a/", safe, client)["title"] == "Test & Page"
    assert fetch("https://example.com/redir", safe, client) is None      # redirect into the LAN refused
    assert fetch("https://example.com/pdf", safe, client) is None        # binary -> cloud
    assert fetch("https://example.com/blocked", safe, client) is None    # 403 -> cloud
    assert fetch("https://example.com/spa", safe, client) is None        # JS shell -> cloud
    print("local-extract selftest ok")


if __name__ == "__main__":
    selftest()
