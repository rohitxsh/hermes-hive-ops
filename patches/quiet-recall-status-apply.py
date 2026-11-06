#!/usr/bin/python3
"""Local Hermes patch (2026-11-06, owner: only real agent messages in chat): the memory recall indicator
("🧠 Holographic — recalled 2 memories") and the "Session is free; loading the latest transcript..." notice stay out
of messaging chats (Discord, Telegram, ...), like the compaction chatter Hermes already filters there. The CLI and
TUI still show them, and the gateway logs them at debug. Idempotent; `--check` reports; `--test` runs the filter
with Hermes's venv python. Re-run after `hermes update`, then restart the gateway."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F = ROOT / "gateway/run.py"
MARK = "local patch (2026-11-06): quiet recall status"
OLD = '    r"|skipping\\s+concurrent\\s+compression"\n'
NEW = OLD + (f'    # {MARK}: memory recall indicator and transcript reload notice\n'
             '    r"|[—-]\\s+recalled\\s+(?:\\d+\\s+memor(?:y|ies)|relevant\\s+memory)"\n'
             '    r"|session\\s+is\\s+free;\\s+loading\\s+the\\s+latest\\s+transcript"\n')


def selftest():
    sys.path.insert(0, str(ROOT))
    import gateway.run as r
    drop = ["🧠 Holographic — recalled 2 memories", "🧠 Holographic — recalled 1 memory",
            "🧠 Honcho — recalled relevant memory  🧠 Holographic — recalled 3 memories",
            "Session is free; loading the latest transcript..."]
    keep = ["I recalled 2 memories about your trip and booked the hotel.", "PR #38 merged."]
    for t in drop:
        assert r._TELEGRAM_NOISY_STATUS_RE.search(t), t
    for t in keep:
        assert not r._TELEGRAM_NOISY_STATUS_RE.search(t), t
    print(f"selftest ok {len(drop) + len(keep)} cases")


t = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    print("ok" if MARK in t else "missing")
    sys.exit(0 if MARK in t else 1)
if "--test" in sys.argv:
    selftest()
    sys.exit(0)
if MARK not in t:
    assert t.count(OLD) == 1, "gateway/run.py: anchor not found once; upstream changed, patch by hand"
    t = t.replace(OLD, NEW)
    compile(t, str(F), "exec")
    bak = Path(str(F) + ".bak-2026-11-06-quietrecall")
    if not bak.exists():
        shutil.copy2(F, bak)
    F.write_text(t, encoding="utf-8")
    print("patched", F)
print("ok")
