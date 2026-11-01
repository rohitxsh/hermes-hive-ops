#!/usr/bin/python3
"""Local Hermes patch (2026-11-02): when an agent blocks a card with the same
reason again and again, Hermes moves it to triage ("block_loop_detected", needs a decision) and wakes its owner. But the
auto-decomposer treats every triage card as a new idea: a held card was re-specified and promoted every ~3 minutes and once
fanned out into six duplicate QA cards. This patch makes the auto-decomposer skip only cards whose latest routing
event is block_loop_detected; their owner (the PM agent) routes them. New triage cards are still auto-decomposed, and no
setting changes. Idempotent; `--check` only reports; `--test` runs the self-test with Hermes's venv python. Re-run after
`hermes update` if the self-check says it's missing, then restart the gateway when idle."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F = ROOT / "gateway/kanban_watchers_dispatcher.py"
TAG = ".bak-2026-11-02-loophold"
MARK = "local patch (2026-11-02): loop-held triage cards"

A = ("                    for tid in triage_ids:\n"
     "                        if attempted >= auto_decompose_per_tick:\n"
     "                            break\n"
     "                        attempted += 1\n")
B = ("                    for tid in triage_ids:\n"
     "                        if attempted >= auto_decompose_per_tick:\n"
     "                            break\n"
     f"                        if _loop_held(tid):  # {MARK}\n"
     "                            continue\n"
     "                        attempted += 1\n")
H = f'''

def _latest_routing_event(conn, tid):
    """{MARK}: the latest event that put a card into or out of triage."""
    row = conn.execute(
        "SELECT kind FROM task_events WHERE task_id = ? AND kind IN "
        "('block_loop_detected', 'promoted', 'specified', 'decomposed', 'created') "
        "ORDER BY created_at DESC, id DESC LIMIT 1", (tid,)).fetchone()
    return row[0] if row else None


def _loop_held(tid):
    """{MARK}: True when Hermes sent this card to triage for looping blocks; its owner routes it,
    so the auto-decomposer must not re-specify, promote or fan it out. Fails open (False) on errors."""
    try:
        from hermes_cli import kanban_db_connect as _kbc
        with _kbc.connect_closing() as conn:
            return _latest_routing_event(conn, tid) == "block_loop_detected"
    except Exception:
        return False
'''


def selftest():
    import sqlite3
    sys.path.insert(0, str(ROOT))
    from gateway import kanban_watchers_dispatcher as d
    c = sqlite3.connect(":memory:")
    c.execute("create table task_events (id integer primary key, task_id text, run_id int, kind text, payload text, created_at int)")
    ev = [("t1", "created", 1), ("t1", "promoted", 2), ("t1", "block_loop_detected", 3), ("t1", "commented", 4),
          ("t2", "created", 1), ("t2", "block_loop_detected", 2), ("t2", "promoted", 3),
          ("t3", "created", 1)]
    c.executemany("insert into task_events (task_id, kind, created_at) values (?, ?, ?)", ev)
    assert d._latest_routing_event(c, "t1") == "block_loop_detected"   # looped into triage: held
    assert d._latest_routing_event(c, "t2") == "promoted"              # routed since: not held
    assert d._latest_routing_event(c, "t3") == "created"               # new triage card: decomposed as usual
    assert d._latest_routing_event(c, "nope") is None
    assert d._loop_held("t_does_not_exist") is False                   # unknown card or no board: fail open
    print("selftest ok 5 cases")


s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    ok = MARK in s
    print("ok" if ok else "missing")
    sys.exit(0 if ok else 1)
if "--test" in sys.argv:
    selftest()
    sys.exit(0)
if MARK not in s:
    assert s.count(A) == 1, "auto_decompose_tick anchor not found once; upstream changed, patch by hand"
    s = s.replace(A, B).rstrip("\n") + "\n" + H
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
