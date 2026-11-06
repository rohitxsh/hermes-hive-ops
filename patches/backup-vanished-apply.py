#!/usr/bin/python3
"""Local Hermes patch (2026-11-02): `hermes backup` lists every file first and then archives them. On a busy VM the
cron scheduler deletes its own short-lived files in between (job output logs, admission records, external-worker
stderr), so the nightly full backup failed as "incomplete" and old backups stopped being pruned. This patch counts a
file as skipped, not as an error, only when it vanished (FileNotFoundError) AND lives in cron/output/,
cron/admissions/ or cron/external-workers/ (root or a profile), or in a Kanban card's scratch workspace
(kanban/workspaces/, whose workers delete their own temp files; added 2026-11-06). Any other missing or unreadable file still fails the
backup. Idempotent; `--check` only reports; `--test` runs the self-test with Hermes's venv python. Re-run after
`hermes update` if the self-check says it's missing."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F = ROOT / "hermes_cli/backup.py"
TAG = ".bak-2026-11-02-vanished"
MARK = "local patch (2026-11-02): vanished cron files"

A1 = ("    errors = []\n"
      "    t0 = time.monotonic()\n")
B1 = ("    errors = []\n"
      f"    vanished = []  # {MARK}\n"
      "    t0 = time.monotonic()\n")
A2 = '            on_error=lambda rel, exc: errors.append(f"{rel}: {exc}"))\n'
B2 = '            on_error=lambda rel, exc: (vanished if _vanished_ok(rel, exc) else errors).append(f"{rel}: {exc}"))\n'
A3 = ("    if errors:\n"
      "        _print_capped(f\"\\n  Archive kept, but {len(errors)} file(s) could not be added:\", errors, \"  \")\n")
B3 = ("    if vanished:\n"
      "        print(f\"\\n  Skipped {len(vanished)} short-lived cron file(s) deleted by the scheduler while the backup ran\")\n" + A3)
H = f'''

_VANISH_DIRS = ("cron/output/", "cron/admissions/", "cron/external-workers/", "kanban/workspaces/")


def _vanished_ok(rel, exc) -> bool:
    """{MARK}: True only for a file that disappeared mid-backup inside the scheduler's short-lived folders."""
    path = str(rel).replace("\\\\", "/")
    if path.startswith("profiles/"):
        parts = path.split("/", 2)
        path = parts[2] if len(parts) == 3 else ""
    return isinstance(exc, FileNotFoundError) and path.startswith(_VANISH_DIRS)
'''


def selftest():
    sys.path.insert(0, str(ROOT))
    from hermes_cli import backup as b
    nf = FileNotFoundError(2, "No such file or directory")
    assert b._vanished_ok("cron/output/039c/2026-11-01_18-10-06.md", nf)
    assert b._vanished_ok("cron/admissions/289e.json", nf)
    assert b._vanished_ok("profiles/project-dev/cron/external-workers/19.stderr", nf)
    assert b._vanished_ok("kanban/workspaces/t_1/browser-raw-20261106-0234.log", nf)
    assert not b._vanished_ok("kanban.db", nf)
    assert not b._vanished_ok("cron/jobs.json", nf)                       # durable cron state still fails
    assert not b._vanished_ok("state.db", nf)
    assert not b._vanished_ok("cron/output/x.md", PermissionError(13, "denied"))  # unreadable still fails
    print("selftest ok 8 cases")


s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    ok = MARK in s
    print("ok" if ok else "missing")
    sys.exit(0 if ok else 1)
if "--test" in sys.argv:
    selftest()
    sys.exit(0)
if MARK in s and '("cron/output/", "cron/admissions/", "cron/external-workers/")' in s:  # an install patched before kanban/workspaces/ was added
    s = s.replace('_VANISH_DIRS = ("cron/output/", "cron/admissions/", "cron/external-workers/")', '_VANISH_DIRS = ("cron/output/", "cron/admissions/", "cron/external-workers/", "kanban/workspaces/")')
    compile(s, str(F), "exec")
    F.write_text(s, encoding="utf-8")
    print("updated", F)
if MARK not in s:
    for a in (A1, A2, A3):
        assert s.count(a) == 1, f"backup.py anchor not found once ({a.strip()[:40]}); upstream changed, patch by hand"
    s = s.replace(A1, B1).replace(A2, B2).replace(A3, B3).rstrip("\n") + "\n" + H
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
