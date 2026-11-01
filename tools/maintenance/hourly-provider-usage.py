#!/usr/bin/env python3
"""Hourly account usage report; uses existing read-only quota readers, no LLM."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import math
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path.home() / "agents/src/quota"))
import quota_lib as q


def reset_summary(value, now):
    try:
        reset = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if reset.tzinfo is None:
            return "reset unavailable"
        remaining = (reset - now).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return "reset unavailable"
    stamp = reset.astimezone().strftime("%d %b %Y, %H:%M %Z")
    if remaining <= 0:
        return f"reset {stamp} (time passed; awaiting provider refresh)"
    minutes = math.ceil(remaining / 60)
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    return f"resets {stamp} ({days}d {hours}h {minutes}m remaining)"


def metric(windows, label, now):
    if windows is None:
        return "unavailable"
    window = next((w for w in windows if w.get("label") == label), None)
    if window is None:
        return "not reported by provider"
    try:
        used = float(window["used"])
        if not math.isfinite(used) or not 0 <= used <= 100:
            return "unavailable"
    except (KeyError, TypeError, ValueError):
        return "unavailable"
    return f"{used:g}% used · {reset_summary(window.get('resets_at'), now)}"


def fetch(provider):
    try:
        return q.usage(provider, fresh=True)
    except Exception:
        # Never include raw errors: upstream exceptions may contain credentials.
        return None


def main():
    with ThreadPoolExecutor(max_workers=2) as pool:
        codex = pool.submit(fetch, "openai-codex")
        claude = pool.submit(fetch, "claude")
        readings = [("Codex", codex.result()), ("Claude", claude.result())]
    now = datetime.now(timezone.utc)
    stamp = now.astimezone().strftime("%d %b %Y, %H:%M %Z")
    print(f"**Account usage — {stamp}**")
    for name, windows in readings:
        labels = [("weekly", "weekly")] if name == "Codex" else [("5h", "5-hour"), ("weekly", "weekly")]
        for title, label in labels:
            print(f"- **{name} {title}:** {metric(windows, label, now)}")


if __name__ == "__main__":
    main()
