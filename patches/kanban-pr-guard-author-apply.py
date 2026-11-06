#!/usr/bin/python3
"""Local Hermes patch (2026-11-03): the Kanban duplicate-PR guard counts only the assignee's own comments.
The dispatcher holds a ready card for 24 h when any comment in that window contains a GitHub PR URL ("prior worker
already opened a PR"). A PM or reviewer citing a PR as a reference (for example "see .../pull/33") held unrelated
cards the same way: "kanban dispatcher stuck ... active_pr=1" for a day at a time. Now only comments written by the
card's current assignee count (an empty author or assignee still counts: fail closed). A reassign after the PR comment
still lifts the guard, as upstream. Idempotent; `--check` reports; `--test` checks the split on a temp board.
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

t = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    print("ok" if MARK in t else "missing")
    sys.exit(0 if MARK in t else 1)
if "--test" in sys.argv:
    assert NEW in t and t.count(MARK) == 1, "patch not applied"
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
print("ok")
