#!/usr/bin/python3
"""Local Hermes patch (2026-11-03): typing indicator for queued Discord turns. Before a queued follow-up runs, the
gateway calls send_typing to restart the indicator, but Discord's send_typing is a no-op while its 12s POST loop is
alive, and posting the first reply has just hidden the bot's typing in clients. So the queued turn showed no typing
for up to 12s (often all of it). Stop the loop first so the restart POSTs at once. Idempotent; `--check` reports.
Re-run after `hermes update`, then restart the gateway."""
import shutil
import sys
from pathlib import Path

F = Path.home() / ".hermes/hermes-agent/gateway/run_turn.py"
MARK = "local patch (2026-11-03): queued-turn typing restart"
OLD = '''        # Restart the typing indicator; the outer typing task may be stale.
        if _clear_adapter:
            with suppress(Exception):
                await _clear_adapter.send_typing(source.chat_id, metadata=_status_thread_metadata)
'''
NEW = f'''        # Restart the typing indicator; the outer typing task may be stale.
        if _clear_adapter:
            with suppress(Exception):
                # {MARK}: Discord's send_typing is a no-op while its loop runs.
                await _clear_adapter._stop_typing_quietly(source.chat_id, _status_thread_metadata)
            with suppress(Exception):
                await _clear_adapter.send_typing(source.chat_id, metadata=_status_thread_metadata)
'''
t = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    print("ok" if MARK in t else "missing")
    sys.exit(0 if MARK in t else 1)
if MARK not in t:
    assert t.count(OLD) == 1, "run_turn.py: anchor not found once; upstream changed, patch by hand"
    t = t.replace(OLD, NEW)
    compile(t, str(F), "exec")
    bak = Path(str(F) + ".bak-2026-11-03-queuedtyping")
    if not bak.exists():
        shutil.copy2(F, bak)
    F.write_text(t, encoding="utf-8")
    print("patched", F)
print("ok")
