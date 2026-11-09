#!/usr/bin/python3
"""Local Hermes patch (the owner, 2026-11-09): a message that arrives while the gateway is draining for a restart gets
a plain "restarting, send it again in a minute" reply instead of the generic "Sorry, I encountered an error."
(the turn is refused with RuntimeStoreError('runtime_draining') and nothing replays it after the restart).

One edit in gateway/platforms/base.py `_notify_turn_error`. Idempotent; `--check` only reports. Re-run after
`hermes update` if the self-check says it's missing, then restart the gateway when idle."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
TAG = ".bak-2026-11-09-drain-reply"
MARK = "local patch (2026-11-09): drain reply"
TEXT = ("♻️ I'm restarting for a moment, so I didn't get to this message. "
        "Please send it again in a minute and I'll pick it up.")
EDITS = [
    (ROOT / "gateway/platforms/base.py",
     "            _thread_metadata = _thread_metadata_for_event(event)\n"
     "            error_detail = str(e)[:300] if str(e) else t(\"gateway.notify.turn_error_no_details\")\n",
     "            _thread_metadata = _thread_metadata_for_event(event)\n"
     f"            if str(e) == \"runtime_draining\":  # {MARK}: a restart is draining; say so plainly\n"
     f"                await self.send(chat_id=event.source.chat_id, content={TEXT!r}, metadata=_thread_metadata)\n"
     "                return _thread_metadata\n"
     "            error_detail = str(e)[:300] if str(e) else t(\"gateway.notify.turn_error_no_details\")\n"),
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
    print("drain reply: ok")


if __name__ == "__main__":
    main()
