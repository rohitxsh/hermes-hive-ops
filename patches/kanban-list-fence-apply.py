#!/usr/bin/python3
"""Local Hermes patch (2026-11-04): a delegated child (HERMES_DELEGATED_CHILD_CONTEXT) is fenced from writing the Kanban
board, and `hermes kanban list` refreshes the ready lane (a write) before listing, so the read-only listing failed with
PermissionError inside every delegated helper. The listing now skips only that refresh when the fence refuses it.
Upstream issue: NousResearch/hermes-agent#148926. Idempotent; `--check` only reports. Lives in
~/agents/src/hermes-local-patches/; re-run after `hermes update` if the self-check says it's missing."""
import shutil
import sys
from pathlib import Path

F = Path.home() / ".hermes/hermes-agent/hermes_cli/kanban.py"
TAG = ".bak-2026-11-04-listfence"
MARK = "local patch (2026-11-04): a fenced worker may still read the board"
PAIRS = [
    ("        kb.recompute_ready(conn)\n",
     f"        # {MARK}; skip only this refresh write\n"
     "        try:\n"
     "            kb.recompute_ready(conn)\n"
     "        except PermissionError:\n"
     "            pass\n"),
]

s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    print("ok" if MARK in s else "missing")
    sys.exit(0 if MARK in s else 1)
if MARK not in s:
    for a, b in PAIRS:
        assert s.count(a) == 1, ("anchor not found once; upstream changed, patch by hand", a[:60])
        s = s.replace(a, b)
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
