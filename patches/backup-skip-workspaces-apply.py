#!/usr/bin/python3
"""Local Hermes patch (2026-11-19): `hermes backup` (and the pre-update backup) skips kanban/workspaces and
the logs/process-output and logs/process-results folders.

Why: Kanban card workspaces hold test builds, Flutter environments and evidence copies (59 GB on one VM). The nightly
backup walked all of it, took a long time, failed on files a running card deleted mid-walk, and the wrapper then
deleted those entries from the zip anyway. logs/process-output and logs/process-results (shared and per profile) hold the output files of
running background processes, which agents delete while the backup walks them ("Errno 2"), so backups during busy
hours failed. The board itself (kanban.db) and all other logs are still backed up; the VM image keeps the workspaces.
Idempotent; `--check` only reports; `--test` checks the rule with Hermes's venv python. Re-run after `hermes update`."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F = ROOT / "hermes_cli/backup.py"
TAG = ".bak-2026-11-19-skip-workspaces"
MARK = "local patch (2026-11-19b): skip Kanban card workspaces and live process output"
OLD_MARK = "local patch (2026-11-19): skip Kanban card workspaces"
ANCHOR = ('    """Return True if *rel_path* (relative to hermes root) should be skipped."""\n'
          '    parts = rel_path.parts\n')
FIRST = f'    if parts[:2] == ("kanban", "workspaces"):  # {OLD_MARK}\n        return True\n'
NEW = ANCHOR + (f'    # {MARK}\n'
                '    if parts[:2] == ("kanban", "workspaces") or any(\n'
                '            parts[i:i + 2] in (("logs", "process-output"), ("logs", "process-results")) for i in range(len(parts) - 1)):\n'
                '        return True\n')

if "--test" in sys.argv:
    sys.path.insert(0, str(ROOT))
    from hermes_cli import backup as b
    assert b._should_exclude(Path("kanban/workspaces")) and b._should_exclude(Path("kanban/workspaces/t_1/a.txt"))
    assert not b._should_exclude(Path("kanban.db")) and not b._should_exclude(Path("skills/x/workspaces/a.md"))
    assert b._should_exclude(Path("profiles/qa/logs/process-output/p.log"))
    assert b._should_exclude(Path("logs/process-output/x")) and b._should_exclude(Path("profiles/d/logs/process-results/p.json"))
    assert not b._should_exclude(Path("profiles/qa/logs/agent.log"))
    print("selftest ok 7 cases")
    sys.exit(0)
s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    print("ok" if MARK in s else "missing")
    sys.exit(0 if MARK in s else 1)
if MARK not in s:
    s = s.replace(ANCHOR + FIRST, ANCHOR)  # drop the first version of this patch
    i = s.find("    # local patch (2026-11-19): skip Kanban card workspaces and live process output\n")
    if i >= 0:  # and the second
        j = s.index("        return True\n", i) + len("        return True\n")
        s = s[:i] + s[j:]
    assert s.count(ANCHOR) == 1, "backup._should_exclude anchor not found once; upstream changed, patch by hand"
    s = s.replace(ANCHOR, NEW)
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
