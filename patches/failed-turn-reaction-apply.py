#!/usr/bin/python3
"""Local Hermes patch (the owner, 2026-10-30): a turn that failed (quota/rate limit, provider error, crash) gets the
❌ reaction instead of ✅, even when its error reply was delivered. Upstream marks ✅ whenever the reply was sent.

Two edits: gateway/run_turn.py flags the event when the agent result says failed; gateway/platforms/base.py
counts a flagged event as a failure. Idempotent; `--check` only reports. Lives in ~/agents/src/hermes-local-patches/;
re-run after `hermes update` if the self-check says it's missing, then restart the gateway when idle."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
TAG = ".bak-2026-10-30-reaction"
MARK = "local patch (2026-10-30): failed turn reaction"
EDITS = [
    (ROOT / "gateway/run_turn.py",
     "                if isinstance(agent_result.get(\"_notification_reply_muted\"), bool):\n"
     "                    event._notification_reply_muted = agent_result[\"_notification_reply_muted\"]\n",
     "                if isinstance(agent_result.get(\"_notification_reply_muted\"), bool):\n"
     "                    event._notification_reply_muted = agent_result[\"_notification_reply_muted\"]\n"
     f"                # {MARK}: the adapter marks ❌ instead of ✅ when the turn failed\n"
     "                event._hermes_turn_failed = bool(agent_result.get(\"failed\"))\n"),
    (ROOT / "gateway/platforms/base.py",
     "            processing_ok = delivery_succeeded if delivery_attempted else not bool(response)\n",
     "            processing_ok = delivery_succeeded if delivery_attempted else not bool(response)\n"
     f"            # {MARK}: a delivered error reply is still a failed turn\n"
     "            processing_ok = processing_ok and not getattr(event, \"_hermes_turn_failed\", False)\n"),
]


def main():
    check = "--check" in sys.argv
    missing = []
    for path, old, new in EDITS:
        s = path.read_text(encoding="utf-8")
        if new in s:
            continue
        if check:
            missing.append(path.name)
            continue
        assert s.count(old) == 1, f"{path}: anchor not found once ({s.count(old)}); upstream changed, patch by hand"
        if not Path(str(path) + TAG).exists():
            shutil.copy2(path, str(path) + TAG)
        path.write_text(s.replace(old, new), encoding="utf-8")
        print("patched", path)
    if check:
        print("missing: " + ", ".join(missing) if missing else "ok")
        sys.exit(1 if missing else 0)
    for path, _, new in EDITS:
        assert new in path.read_text(encoding="utf-8"), path
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    print("ok")


if __name__ == "__main__":
    main()
