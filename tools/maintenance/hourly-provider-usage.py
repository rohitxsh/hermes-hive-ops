#!/usr/bin/env python3
"""Hourly account usage report; uses existing read-only quota readers, no LLM."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import math
import subprocess
import shutil
import json
import os
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


ACTIONS_MULTIPLIER = {"actions_linux": 1, "actions_windows": 2, "actions_macos": 10}  # GitHub's included-minute rates


def actions_line():
    """GitHub Actions minutes for GITHUB_BILLING_ORG this month against GITHUB_ACTIONS_INCLUDED_MINUTES (default 3000,
    the Team plan). Hosted jobs stop starting once they are used up unless the org has a spending budget."""
    org = os.environ.get("GITHUB_BILLING_ORG")
    if not org:
        return None
    gh = shutil.which("gh") or os.path.expanduser("~/.local/bin/gh")
    try:
        r = subprocess.run([gh, "api", f"organizations/{org}/settings/billing/usage/summary"],
                           capture_output=True, text=True, timeout=60)
        items = json.loads(r.stdout or "{}").get("usageItems") or []
    except (OSError, ValueError, subprocess.SubprocessError):
        return f"- **GitHub Actions ({org}):** unavailable"
    used = sum(float(i.get("grossQuantity") or 0) * ACTIONS_MULTIPLIER[i.get("sku")]
               for i in items if i.get("sku") in ACTIONS_MULTIPLIER)
    try:
        included = float(os.environ.get("GITHUB_ACTIONS_INCLUDED_MINUTES") or 3000)
    except ValueError:
        included = 3000.0
    pct = used / included * 100 if included else 0
    line = f"- **GitHub Actions ({org}):** {used:.0f} of {included:.0f} included minutes used this month ({pct:.0f}%)"
    if pct >= 100:
        line += ". ⚠️ Used up: hosted CI won't start until next month unless the org sets an Actions budget (Billing & plans)."
    elif pct >= 80:
        line += ". ⚠️ Nearly used up: set an Actions budget or slow CI down before it stops."
    return line


def main():
    with ThreadPoolExecutor(max_workers=2) as pool:
        codex = pool.submit(fetch, "openai-codex")
        claude = pool.submit(fetch, "claude")
        readings = [("Codex", codex.result()), ("Claude", claude.result())]
    now = datetime.now(timezone.utc)
    stamp = now.astimezone().strftime("%d %b %Y, %H:%M %Z")
    # USAGE_POST_SILENT=1: Discord "@silent" message (visible, no push or sound; needs the team-notification patch).
    # It shares the heading line: alone on line 1, cron would read it as [SILENT] and post nothing.
    print(("@silent " if os.environ.get("USAGE_POST_SILENT") == "1" else "") + f"**Account usage — {stamp}**")
    for name, windows in readings:
        labels = [("weekly", "weekly")] if name == "Codex" else [("5h", "5-hour"), ("weekly", "weekly")]
        has = {w.get("label") for w in windows or []}
        if name == "Codex" and "weekly" not in has and "limit" in has:  # a used-up account reports one "limit" window
            labels = [("limit", "limit")]
        for title, label in labels:
            print(f"- **{name} {title}:** {metric(windows, label, now)}")
    actions = actions_line()
    if actions:
        print(actions)
    full = [name for name, windows in readings if any((w.get("used") or 0) >= 100 for w in windows or [])]
    if full:  # a reset can sometimes be claimed on the provider's account page before the scheduled one
        print(f"- ⚠️ **{' and '.join(full)} at 100%:** check whether a limit reset is available for the account.")


if __name__ == "__main__":
    main()
