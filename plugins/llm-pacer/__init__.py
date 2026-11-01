"""Minimum gap between this profile's model API calls, so bursts (parallel turns, tool loops) don't trip
rate limits. Runs in the turn's own thread before each request; other turns aren't blocked."""
from __future__ import annotations

import logging
import os
import threading
import time

GAP = float(os.environ.get("HERMES_LLM_MIN_GAP_SECONDS", "2"))
_lock = threading.Lock()
_next_slot = 0.0


def reserve(now: float) -> float:
    """Seconds to wait before this request may start; books the next free slot."""
    global _next_slot
    with _lock:
        start = max(now, _next_slot)
        _next_slot = start + GAP
        return start - now


def pre_api_request(**_kwargs) -> None:
    wait = reserve(time.monotonic())
    if wait > 0:
        logging.getLogger(__name__).info("llm-pacer: waiting %.1fs before the next model call", wait)
        time.sleep(min(wait, 30.0))


def register(ctx) -> None:
    ctx.register_hook("pre_api_request", pre_api_request)
