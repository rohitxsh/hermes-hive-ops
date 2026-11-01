"""Append a Codex quota warning to every reply while the 5-hour or weekly window is at or above THRESHOLD%.

Usage comes from Hermes's own read-only Codex usage fetch (the same data as `hermes usage`), cached for
CACHE_S so a busy chat costs at most one usage request a minute. Any failure leaves the reply unchanged.
"""

import logging
import threading
import time
from datetime import timedelta, timezone

THRESHOLD = 90.0
CACHE_S = 60.0
# reset times are shown in the machine's local time zone
NAMES = {"Session": "5-hour", "Weekly": "weekly"}

log = logging.getLogger(__name__)
_lock = threading.Lock()
_state = {"at": float("-inf"), "snap": None}


def _fetch():
    from agent.account_usage import fetch_account_usage
    return fetch_account_usage("openai-codex", read_only=True)


def _snapshot():
    with _lock:
        if time.monotonic() - _state["at"] < CACHE_S:
            return _state["snap"]
        _state["at"] = time.monotonic()  # failures wait CACHE_S too, so a dead endpoint isn't hit every reply
    try:
        snap = _fetch()
    except Exception as exc:
        log.warning("codex-usage-alert: usage fetch failed: %s", exc)
        snap = None
    with _lock:
        if snap is not None:
            _state["snap"] = snap
        return _state["snap"]


def _alert_line(snap):
    if snap is None:
        return None
    try:
        if time.time() - snap.fetched_at.timestamp() > 15 * 60:
            return None  # stale numbers would mislead
    except Exception:
        return None
    parts = []
    for w in snap.windows:
        if getattr(w, "scope", "account") != "account" or w.used_percent is None or w.used_percent < THRESHOLD:
            continue
        reset = f", resets {w.reset_at.astimezone():%a %d %b %H:%M %Z}" if w.reset_at else ""
        parts.append(f"{NAMES.get(w.label, w.label)} limit {w.used_percent:.0f}% used{reset}")
    return f"⚠️ Codex usage alert (automatic): {'; '.join(parts)}" if parts else None


def transform_llm_output(response_text="", **kwargs):
    if not response_text:
        return None
    line = _alert_line(_snapshot())
    return f"{response_text}\n\n{line}" if line else None


def register(ctx):
    ctx.register_hook("transform_llm_output", transform_llm_output)
