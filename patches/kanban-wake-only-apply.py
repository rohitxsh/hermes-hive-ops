#!/usr/bin/python3
"""Local Hermes patch (2026-11-02): Kanban chat subscriptions wake the agent instead of posting raw pings. When a
card is created from a chat (kanban_create auto-subscribe, or /kanban from chat), Hermes subscribes that chat in
"notify+wake" mode: it posts a raw "✓ … Kanban t_… done" / "⏸ … blocked" message with the card ID, uploads every file
named in the completion summary, and also wakes the agent, which then answers too. In a human thread that doubles
messages and files. With this patch those subscriptions use "wake": only the agent is woken, and it writes one
human-readable update. Existing subscriptions are switched with `hermes kanban notify-subscribe … --delivery-mode wake`.
Idempotent; `--check` only reports; `--test` checks the patched source. Re-run after `hermes update`, then restart."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
MARK = "local patch (2026-11-02): kanban wake-only subscriptions"
EDITS = [
    (ROOT / "tools/kanban_tools.py",
     '        delivery_mode="notify+wake" if platform != "tui" else None,\n',
     f'        delivery_mode="wake" if platform != "tui" else None,  # {MARK}\n'),
    (ROOT / "gateway/slash_commands.py",
     '                    delivery_mode="notify+wake", delivery_metadata=delivery_metadata)\n',
     f'                    delivery_mode="wake", delivery_metadata=delivery_metadata)  # {MARK}\n'),
]
TAG = ".bak-2026-11-02-wakeonly"

texts = {f: f.read_text(encoding="utf-8") for f, _, _ in EDITS}
if "--check" in sys.argv:
    ok = all(MARK in t for t in texts.values())
    print("ok" if ok else "missing")
    sys.exit(0 if ok else 1)
if "--test" in sys.argv:
    for f, old, new in EDITS:
        t = texts[f]
        assert new in t and old not in t, f
        compile(t, str(f), "exec")
    print("selftest ok 2 files")
    sys.exit(0)
for f, old, new in EDITS:
    t = texts[f]
    if MARK in t:
        continue
    assert t.count(old) == 1, f"{f.name}: anchor not found once; upstream changed, patch by hand"
    t = t.replace(old, new)
    compile(t, str(f), "exec")
    if not Path(str(f) + TAG).exists():
        shutil.copy2(f, str(f) + TAG)
    f.write_text(t, encoding="utf-8")
    print("patched", f)
print("ok")
