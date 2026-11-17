#!/usr/bin/python3
"""Local Hermes patch (2026-11-18): `hermes kanban schedule <id> "<reason>"` on a card that is already scheduled
returned "cannot schedule", so an admin could not correct a stale wait reason (or add SCHEDULED_UNTIL) without
`unblock` + `schedule`, which lets the dispatcher claim the card in between. With this patch a scheduled card can be
re-parked with a new reason: only a new "scheduled" event is written (no run, status or claim change). Workers are
unaffected: their kanban_schedule passes their run id, and that path is unchanged.
Idempotent; `--check` only reports; `--test` runs a functional self-test on a temporary board with Hermes's venv
python. Re-run after `hermes update`."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F = ROOT / "hermes_cli/kanban_db.py"
TAG = ".bak-2026-11-18-reschedule"
MARK = "local patch (2026-11-18): re-park a scheduled task with a new reason"
OLD = ('            params.append(int(expected_run_id))\n'
       '        if conn.execute(sql, params).rowcount != 1:\n'
       '            return False\n'
       '        run_id = _end_or_synthesize_run(\n'
       '            conn, task_id, outcome="scheduled"')
NEW = ('            params.append(int(expected_run_id))\n'
       '        if conn.execute(sql, params).rowcount != 1:\n'
       f'            # {MARK} (admin CLI/dashboard only: workers pass their run id)\n'
       '            if expected_run_id is None and reason and conn.execute(\n'
       '                    "SELECT 1 FROM tasks WHERE id = ? AND status = \'scheduled\'", (task_id,)).fetchone():\n'
       '                _append_event(conn, task_id, "scheduled", {"reason": reason})\n'
       '                return True\n'
       '            return False\n'
       '        run_id = _end_or_synthesize_run(\n'
       '            conn, task_id, outcome="scheduled"')


def selftest():
    home = tempfile.mkdtemp(prefix="kb-resched-")
    os.environ["HERMES_HOME"] = home
    sys.path.insert(0, str(ROOT))
    from hermes_cli import kanban_db as kb
    from hermes_cli import kanban_db_connect as kbc
    try:
        with kbc.connect() as conn:
            t = kb.create_task(conn, title="x", assignee="ops")
            assert kb.schedule_task(conn, t, reason="first") is True
            assert kb.schedule_task(conn, t, reason="second SCHEDULED_UNTIL=2030-01-01") is True   # the fix
            assert kb.get_task(conn, t).status == "scheduled" and kb.claim_task(conn, t) is None
            ev = [r[0] for r in conn.execute("select payload from task_events where task_id=? and kind='scheduled' "
                                             "order by id", (t,))]
            assert len(ev) == 2 and "second" in ev[-1], ev
            assert kb.schedule_task(conn, t, reason="") is False                 # no reason: unchanged refusal
            assert kb.schedule_task(conn, t, reason="w", expected_run_id=1) is False  # worker path unchanged
            assert kb.schedule_task(conn, "t_missing0", reason="r") is False
        print("selftest ok 6 cases")
    finally:
        shutil.rmtree(home, ignore_errors=True)


s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    ok = MARK in s
    print("ok" if ok else "missing")
    sys.exit(0 if ok else 1)
if "--test" in sys.argv:
    selftest()
    sys.exit(0)
if MARK not in s:
    assert s.count(OLD) == 1, "kanban_db.schedule_task anchor not found once; upstream changed, patch by hand"
    s = s.replace(OLD, NEW)
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
