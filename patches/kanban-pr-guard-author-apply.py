#!/usr/bin/python3
"""Local Hermes patch (2026-11-03): the Kanban duplicate-PR guard counts only the assignee's own comments.
The dispatcher holds a ready card for 24 h when any comment in that window contains a GitHub PR URL ("prior worker
already opened a PR"). A PM or reviewer citing a PR as a reference (for example "see .../pull/33") held unrelated
cards the same way: "kanban dispatcher stuck ... active_pr=1" for a day at a time. Now only comments written by the
card's current assignee count (an empty author or assignee still counts: fail closed). A reassign after the PR comment
still lifts the guard, as upstream. Second part (2026-11-12): an explicit unblock after the newest PR comment lifts
it too. Workers can't unblock their own card, so an unblock is a deliberate release by a person, the PR-approval
wake-up or the admin (upstream already treats it that way for its recent-success guard); without it, a card resumed
after its PR was approved sat held for up to 24 h. Third part (2026-11-12): a worker that parks its card on a
dependency (dependency_wait) after its PR comment, and is then promoted when the parent finishes, resumes on that same
PR; it is not a crash. Before this, such a card sat in Ready, guarded for the rest of the 24 h. A promotion without that
dependency wait (a crash-blocked card auto-recovering) still stays guarded.
Idempotent; `--check` reports; `--test` checks the split on a temp board.
Re-run after `hermes update`, then restart the gateway."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F = ROOT / "hermes_cli/kanban_db_dispatch.py"
MARK = "local patch (2026-11-03): PR guard counts only the assignee's comments"
OLD = '''    pr_times = [t for t, c in _rows_since(conn, "task_comments", task_id, now - _RESPAWN_GUARD_PR_WINDOW,
                                          cols=", body", unreadable=now)  # duplicate-PR risk: fail closed
                if _RESPAWN_GUARD_PR_URL_RE.search(_kb._lossy_text(c["body"]) or "")]
'''
NEW = f'''    # {MARK}: a PR another role cites is not a PR this card's worker opened.
    _assignee = (conn.execute("SELECT assignee FROM tasks WHERE id = ?", (task_id,)).fetchone() or [None])[0]
    pr_times = [t for t, c in _rows_since(conn, "task_comments", task_id, now - _RESPAWN_GUARD_PR_WINDOW,
                                          cols=", body, author", unreadable=now)  # duplicate-PR risk: fail closed
                if _RESPAWN_GUARD_PR_URL_RE.search(_kb._lossy_text(c["body"]) or "")
                and (not c["author"] or not _assignee or c["author"] == _assignee)]
'''
TAG = ".bak-2026-11-03-prguard"
MARK2 = "local patch (2026-11-12): an explicit unblock lifts the PR guard"
OLD2 = """                "AND kind IN ('assigned', 'changes_requested', 'review_reopened')", cols=", kind, payload", strict=True)):
"""
NEW2 = f"""                # {MARK2}
                "AND kind IN ('assigned', 'changes_requested', 'review_reopened', 'unblocked')", cols=", kind, payload", strict=True)):
"""
MARK3 = "local patch (2026-11-12): a chosen dependency wait, then promotion, resumes the same PR"
OLD3 = """            return None
        return "active_pr"
"""
NEW3 = f"""            return None
        # {MARK3}
        _dep = [t for t, _ in _rows_since(conn, "task_events", task_id, max(pr_times), "AND kind = 'dependency_wait'", strict=True)]
        if _dep and any(_rows_since(conn, "task_events", task_id, min(_dep), "AND kind = 'promoted'", strict=True)):
            return None
        return "active_pr"
"""

t = F.read_text(encoding="utf-8")
ALL = (MARK, MARK2, MARK3)
if "--check" in sys.argv:
    print("ok" if all(m in t for m in ALL) else "missing")
    sys.exit(0 if all(m in t for m in ALL) else 1)
if "--test" in sys.argv:
    assert NEW in t and all(t.count(m) == 1 for m in ALL), "patch not applied"
    sys.path.insert(0, str(ROOT))
    import os, tempfile
    os.environ["HERMES_HOME"] = tempfile.mkdtemp()
    __import__('atexit').register(__import__('shutil').rmtree, os.environ["HERMES_HOME"], True)  # selftest leaves nothing in /tmp
    from hermes_cli import kanban_db as kb
    from hermes_cli import kanban_db_connect as kbc
    from hermes_cli import kanban_db_dispatch as kd
    kbc.init_db()
    conn = kbc.connect()
    url = "https://github.com/example-org/example-repo/pull/33"
    other = kb.create_task(conn, title="cited PR", body="b", assignee="dev")
    kb.add_comment(conn, other, "pm", f"context: see {url}")
    own = kb.create_task(conn, title="own PR", body="b", assignee="dev")
    kb.add_comment(conn, own, "dev", f"opened {url}")
    got = {n: kd.check_respawn_guard(conn, i) for n, i in (("other", other), ("own", own))}
    assert got == {"other": None, "own": "active_pr"}, got
    import time
    time.sleep(1.1)                       # the unblock must be strictly after the PR comment
    assert kb.schedule_task(conn, own, reason="waiting on PR #33") and kb.unblock_task(conn, own)
    assert kd.check_respawn_guard(conn, own) is None, "an explicit unblock must lift the PR guard"
    # a worker that parks on a dependency after its PR comment resumes when promoted; a bare promotion does not
    dep, crash = (kb.create_task(conn, title=n, body="b", assignee="dev") for n in ("dependency wait", "crash recovery"))
    for i in (dep, crash):
        kb.add_comment(conn, i, "dev", f"opened {url}")
    time.sleep(1.1)
    with kb.write_txn(conn):
        kb._append_event(conn, dep, "dependency_wait", {"reason": "waiting on the parent card"})
    time.sleep(1.1)
    with kb.write_txn(conn):
        for i in (dep, crash):
            kb._append_event(conn, i, "promoted", None)
    assert kd.check_respawn_guard(conn, dep) is None, "a chosen dependency wait, then promotion, must lift the guard"
    assert kd.check_respawn_guard(conn, crash) == "active_pr", "a promotion alone must stay guarded"
    print("selftest ok:", got)
    sys.exit(0)
if MARK not in t:
    assert t.count(OLD) == 1, "kanban_db_dispatch.py: anchor not found once; upstream changed, patch by hand"
    t = t.replace(OLD, NEW)
    compile(t, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(t, encoding="utf-8")
    print("patched", F)
if MARK2 not in t:
    assert t.count(OLD2) == 1, "kanban_db_dispatch.py: handoff anchor not found once; upstream changed, patch by hand"
    t = t.replace(OLD2, NEW2)
    compile(t, str(F), "exec")
    F.write_text(t, encoding="utf-8")
    print("patched (unblock lifts the PR guard)", F)
if MARK3 not in t:
    assert t.count(OLD3) == 1, "kanban_db_dispatch.py: active_pr return not found once; upstream changed, patch by hand"
    t = t.replace(OLD3, NEW3)
    compile(t, str(F), "exec")
    F.write_text(t, encoding="utf-8")
    print("patched (a chosen dependency wait, then promotion, lifts the PR guard)", F)
print("ok")
