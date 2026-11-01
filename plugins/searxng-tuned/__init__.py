"""SearXNG (tuned): a local copy of Hermes's bundled SearXNG provider with the vm-a fixes, under its
own name so `hermes update` (which resets the bundled plugins/web/searxng) can't revert them."""
from __future__ import annotations

from .provider import SearXNGWebSearchProvider


def register(ctx) -> None:
    ctx.register_web_search_provider(SearXNGWebSearchProvider())
