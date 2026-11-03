#!/usr/bin/python3
"""Local Hermes patch (2026-11-03): smaller kanban_show for orchestrators. A kanban_show result is ~35k chars, and
more than half is `worker_context` (the card again, pre-formatted for a worker's spawn prompt: ~40%) and the last
50 audit events (~22%). An orchestrator reading someone's card (a pm or design agent) gets the same structured fields without
`worker_context` and with only the last 10 events; the dispatched worker reading its own card still gets everything.
Measured on one team: 58 orchestrator reads a day, median 38.7k chars. Idempotent; `--check` only reports; `--test` checks the
patched source and the worker/orchestrator split. Re-run after `hermes update`, then restart the gateway."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
MARK = "local patch (2026-11-03): compact kanban_show for orchestrators"
F = ROOT / "tools/kanban_tools.py"
OLD = '''    with _board(args.get("board")) as (kb, conn):
        task = _existing_task(kb, conn, tid)
        return json.dumps({
'''
NEW = f'''    with _board(args.get("board")) as (kb, conn):
        task = _existing_task(kb, conn, tid)
        # {MARK}: only the dispatched worker reading its own card needs worker_context and the long event log.
        own = os.environ.get("HERMES_KANBAN_TASK") == tid and _is_dispatcher_owned_worker()
        if not own:
            return json.dumps({{
                "task": _fields(task, _TASK_FIELDS),
                "parents": kb.parent_ids(conn, tid),
                "unsatisfied_parents": [
                    {{"id": pid, "status": status}} for pid, status in kb.unsatisfied_parents(conn, tid)],
                "children": kb.child_ids(conn, tid),
                "comments": [_fields(c, _COMMENT_FIELDS) for c in kb.list_comments(conn, tid)],
                "events": [_fields(e, _EVENT_FIELDS) for e in kb.list_events(conn, tid)[-10:]],
                "runs": [_fields(r, _RUN_FIELDS) for r in kb.list_runs(conn, tid)],
                "note": "Orchestrator view: last 10 events, no worker_context (same facts as above). "
                        "Full event log: `hermes kanban show <id>`."}})
        return json.dumps({{
'''
TAG = ".bak-2026-11-03-showcompact"

t = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    ok = MARK in t
    print("ok" if ok else "missing")
    sys.exit(0 if ok else 1)
if "--test" in sys.argv:
    assert NEW in t and t.count(MARK) == 1, "patch not applied"
    compile(t, str(F), "exec")
    sys.path.insert(0, str(ROOT))
    import json, os, tempfile
    os.environ["HERMES_HOME"] = tempfile.mkdtemp()
    os.environ.pop("HERMES_KANBAN_TASK", None)
    from tools import kanban_tools as kt
    from hermes_cli import kanban_db as kb
    from hermes_cli import kanban_db_connect as kbc
    kbc.init_db()
    conn = kbc.connect()
    tid = kb.create_task(conn, title="compact show test", body="b" * 2000, assignee="x")
    for i in range(20):
        kb.add_comment(conn, tid, "tester", f"c{i}")
    orch = json.loads(kt._handle_show({"task_id": tid}))
    assert "worker_context" not in orch and len(orch["events"]) <= 10 and orch["task"]["id"] == tid, orch.keys()
    os.environ["HERMES_KANBAN_TASK"] = tid
    kt._is_dispatcher_owned_worker = lambda: True
    own = json.loads(kt._handle_show({"task_id": tid}))
    assert "worker_context" in own and "note" not in own, own.keys()
    print(f"selftest ok: orchestrator {len(json.dumps(orch))} chars, worker {len(json.dumps(own))} chars")
    sys.exit(0)
if MARK not in t:
    assert t.count(OLD) == 1, "kanban_tools.py: anchor not found once; upstream changed, patch by hand"
    t = t.replace(OLD, NEW)
    compile(t, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(t, encoding="utf-8")
    print("patched", F)
print("ok")
