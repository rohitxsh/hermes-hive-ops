#!/usr/bin/python3
"""Local Hermes patch (2026-11-02, v2): when an agent blocks a card with the same reason again and again, Hermes moves
it to triage ("block_loop_detected", needs a decision) and wakes its owner. But the auto-decomposer treats every triage
card as a new idea: a held card was re-specified and promoted every ~3 minutes and once fanned out into six duplicate
QA cards. With this patch the auto-decomposer:
- leaves a looped card alone until its owner routes it;
- once the owner has edited or reassigned it after the loop, promotes it to todo AS WRITTEN (no re-specification), so
  the dispatcher starts the new assignee; agents have no tool to release a triage card, and PMs route by editing and
  reassigning;
- treats every other triage card as before. No setting changes.
Idempotent (upgrades v1 in place from its backup); `--check` only reports; `--test` runs the self-test with Hermes's
venv python. Re-run after `hermes update` if the self-check says it's missing, then restart the gateway when idle."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F = ROOT / "gateway/kanban_watchers_dispatcher.py"
TAG = ".bak-2026-11-02-loophold"
MARK = "local patch (2026-11-02): loop-held triage cards v2"
MARK_V1 = "local patch (2026-11-02): loop-held triage cards"

A = ("                    for tid in triage_ids:\n"
     "                        if attempted >= auto_decompose_per_tick:\n"
     "                            break\n"
     "                        attempted += 1\n")
B = ("                    for tid in triage_ids:\n"
     "                        if attempted >= auto_decompose_per_tick:\n"
     "                            break\n"
     f"                        _route = _loop_route(tid)  # {MARK}\n"
     "                        if _route == \"hold\":\n"
     "                            continue\n"
     "                        if _route == \"release\":\n"
     "                            _release_as_written(tid)\n"
     "                            continue\n"
     "                        attempted += 1\n")
H = f'''

_ROUTING_KINDS = ("block_loop_detected", "promoted", "specified", "decomposed", "created")


def _loop_route_from(conn, tid):
    """{MARK}: "hold" while a card Hermes sent to triage for looping blocks waits for its owner; "release" once the
    owner edited or reassigned it after the loop; None for any other triage card (auto-decompose as usual)."""
    rows = conn.execute(
        "SELECT kind FROM task_events WHERE task_id = ? AND kind IN "
        "('block_loop_detected', 'promoted', 'specified', 'decomposed', 'created', 'assigned', 'edited') "
        "ORDER BY created_at DESC, id DESC", (tid,)).fetchall()
    kinds = [r[0] for r in rows]
    last_routing = next((k for k in kinds if k in _ROUTING_KINDS), None)
    if last_routing != "block_loop_detected":
        return None
    return "hold" if kinds[0] == "block_loop_detected" else "release"


def _loop_route(tid):
    try:
        from hermes_cli import kanban_db_connect as _kbc
        with _kbc.connect_closing() as conn:
            return _loop_route_from(conn, tid)
    except Exception:
        return None  # fail open: behave like stock Hermes


def _release_as_written(tid):
    """{MARK}: triage -> todo with the owner's title/body/assignee unchanged."""
    try:
        from hermes_cli import kanban_db as _kb, kanban_db_connect as _kbc
        with _kbc.connect_closing() as conn:
            if _kb.specify_triage_task(conn, tid):
                logger.info("kanban loop-hold: %s released as routed by its owner", tid)
    except Exception:
        logger.exception("kanban loop-hold: release failed for %s", tid)
'''


def selftest():
    import sqlite3
    sys.path.insert(0, str(ROOT))
    from gateway import kanban_watchers_dispatcher as d
    c = sqlite3.connect(":memory:")
    c.execute("create table task_events (id integer primary key, task_id text, run_id int, kind text, payload text, created_at int)")
    ev = {"held": ["created", "promoted", "block_loop_detected", "commented"],
          "routed": ["created", "block_loop_detected", "edited", "assigned"],
          "new": ["created"],
          "later": ["created", "block_loop_detected", "assigned", "specified"],
          "plain": ["created", "assigned"]}
    for tid, kinds in ev.items():
        c.executemany("insert into task_events (task_id, kind, created_at) values (?, ?, ?)", [(tid, k, i) for i, k in enumerate(kinds)])
    assert d._loop_route_from(c, "held") == "hold"
    assert d._loop_route_from(c, "routed") == "release"
    assert d._loop_route_from(c, "new") is None
    assert d._loop_route_from(c, "later") is None      # already promoted after the loop
    assert d._loop_route_from(c, "plain") is None      # a reassignment alone, no loop
    assert d._loop_route("t_does_not_exist") is None   # fail open
    print("selftest ok 6 cases")


s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    ok = MARK in s
    print("ok" if ok else "missing")
    sys.exit(0 if ok else 1)
if "--test" in sys.argv:
    selftest()
    sys.exit(0)
if MARK not in s:
    if MARK_V1 in s:  # upgrade: start again from the pristine copy v1 saved
        s = Path(str(F) + TAG).read_text(encoding="utf-8")
        assert MARK_V1 not in s, "backup is not pristine; patch by hand"
    else:
        shutil.copy2(F, str(F) + TAG)
    assert s.count(A) == 1, "auto_decompose_tick anchor not found once; upstream changed, patch by hand"
    s = s.replace(A, B).rstrip("\n") + "\n" + H
    compile(s, str(F), "exec")
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
