"""Append a short quota note to replies when the profile's main model is nearly used up or replies are
coming from a backup. Reads the profile's own model chain, so model and fallback changes need no edits.

Usage comes from the quota governor's cache (refreshed every 5 minutes); this hook never starts a
fetch, so it adds no delay to a reply. Examples:
  ⚠️ Quota: ChatGPT (Codex) 5-hour 92% used (resets Sat 03:01).
  ⚠️ Quota: ChatGPT (Codex) weekly limit reached (back Thu 23:24). Replies now come from Claude: 5-hour 40% used (60% left), weekly 20% used (80% left).
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time

sys.path.insert(0, os.path.expanduser("~/agents/src/quota"))

THRESHOLD = 90.0
CACHE_S = 60
log = logging.getLogger(__name__)
_lock = threading.Lock()
_memo: dict = {}


def _left(windows, q):
    if windows is None:
        return "usage unknown"
    return ", ".join(f"{w['label']} {w['used']:.0f}% used ({max(0.0, 100 - w['used']):.0f}% left)" for w in windows) or "no limits reported"


def alert_line(providers, getu, auto, q):
    if not providers:
        return None
    first = q.provider_name(providers[0])
    w0 = getu(providers[0])
    if w0 is None:
        return None
    gone = q.used_up(w0)
    if not gone:
        high = [w for w in w0 if w["used"] >= THRESHOLD]
        if not high:
            return None
        return "⚠️ Quota: " + first + " " + "; ".join(
            f"{w['label']} {w['used']:.0f}% used" + (f" (resets {q.local_time(w['resets_at'])})" if w.get("resets_at") else "")
            for w in high) + "."
    resets = [w["resets_at"] for w in gone if w.get("resets_at")]
    back = f" (back {q.local_time(max(resets))})" if resets else ""
    msg = f"⚠️ Quota: {first} {' and '.join(w['label'] for w in gone)} limit reached{back}."
    if len(providers) < 2:
        return msg
    second = q.provider_name(providers[1])
    w1 = getu(providers[1])
    if q.used_up(w1):
        nxt = q.provider_name(providers[2]) if len(providers) > 2 else "nothing"
        return msg + f" {second} is used up too ({q.describe(w1)}); replies come from {nxt} and scheduled work is paused."
    msg += f" Replies now come from {second}: {_left(w1, q)}."
    if auto:
        msg += f" Auto mode pauses at {q.AUTO_CAP:.0f}% of {second}'s 5-hour window or {q.WEEKLY_CAP:.0f}% of its weekly limit."
    return msg


def _profile_state():
    import quota_lib as q
    from hermes_constants import get_hermes_home
    home = str(get_hermes_home())
    with _lock:
        hit = _memo.get(home)
        if hit and time.monotonic() - hit[0] < CACHE_S:
            return hit[1]
    try:
        state = (q.chain(home), q.caps(home))
    except Exception:
        state = ([], False)
    with _lock:
        _memo[home] = (time.monotonic(), state)
    return state


def _silent(text):
    """A [SILENT] / NO_REPLY reply must stay silent: a note after it would turn it into a delivered message."""
    try:
        from gateway.response_filters import is_autonomous_silence_response  # Hermes's own cron/webhook matcher
        return is_autonomous_silence_response(text)
    except Exception:
        lines = [l.strip().upper() for l in str(text or "").splitlines() if l.strip()]
        return bool(lines) and "[SILENT]" in (lines[0], lines[-1])


def transform_llm_output(response_text="", **kwargs):
    if _silent(response_text):
        return None
    try:
        import quota_lib as q
        providers, auto = _profile_state()
        line = alert_line(providers, lambda p: q.usage(p, allow_fetch=False), auto, q)
    except Exception as exc:
        log.warning("quota-alert: %s", exc)
        return None
    if not line or not response_text or line in response_text:
        return None
    return f"{response_text}\n\n{line}"


def register(ctx):
    ctx.register_hook("transform_llm_output", transform_llm_output)


if __name__ == "__main__":  # selftest: python3 __init__.py (from the Hermes checkout, so the real matcher is used)
    assert _silent("Nothing is pending and no warning review is due.\n\n[SILENT]")
    assert _silent("[SILENT]") and _silent("NO_REPLY")
    assert not _silent("Two cards are waiting for you.") and not _silent("this is not [SILENT] mid-sentence")
    assert transform_llm_output("Done.\n\n[SILENT]") is None
    print("quota-alert selftest ok")
