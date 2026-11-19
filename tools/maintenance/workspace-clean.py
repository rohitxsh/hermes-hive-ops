#!/usr/bin/env python3
"""Nightly cleanup of Kanban card workspaces (~/.hermes/kanban/workspaces/<card>), which nothing else removes.

Card workspaces hold worktrees, Flutter test environments and evidence copies; one VM reached 59 GB and about 1% of
disk an hour. This removes:
  - the workspace of a card that is done or archived and has had no board event for DONE_DAYS (default 7), and of a
    card that no longer exists;
  - inside any card that is not running, temporary local-CI copies (top-level `ci-*-env-*` and `*.tmp*` directories)
    older than TEMP_HOURS (default 12).
A running card is never touched. Evidence lives on the card and in GitHub, and Hermes recreates a worktree when a card
reopens. Prints one summary line when it freed space; `--dry-run` lists what it would remove; `--selftest`.
Runs every 6 hours from crontab (`15 */6 * * * python3 ~/agents/src/workspace-clean/workspace-clean.py`).
"""
import glob
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time

H = os.path.expanduser("~")
WS = f"{H}/.hermes/kanban/workspaces"
DB = f"{H}/.hermes/kanban.db"
DONE_DAYS = float(os.environ.get("WORKSPACE_DONE_DAYS", 7))
TEMP_HOURS = float(os.environ.get("WORKSPACE_TEMP_HOURS", 6))
TEMP = re.compile(r"^(ci-[\w.-]+|.*\.tmp[\w.-]*|[\w.-]+-\d{8}-\d{4}\.[A-Za-z0-9]{6})$")  # local-CI runs, mktemp dirs


def size(p):
    total = 0
    for root, _, files in os.walk(p, followlinks=False):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def plan(conn, ws, now):
    """[(path, why)] to remove."""
    out = []
    for d in sorted(os.listdir(ws)):
        p = os.path.join(ws, d)
        if not os.path.isdir(p) or os.path.islink(p):
            continue
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (d,)).fetchone()
        if row is None:
            if now - os.path.getmtime(p) > DONE_DAYS * 86400:
                out.append((p, "card no longer exists"))
            continue
        status = row[0]
        if status == "running":
            continue
        last = conn.execute("SELECT MAX(created_at) FROM task_events WHERE task_id = ?", (d,)).fetchone()[0] or 0
        if status in ("done", "archived") and now - float(last) > DONE_DAYS * 86400:
            out.append((p, f"card {status} {int((now - float(last)) / 86400)} days"))
            continue
        for e in os.listdir(p):
            q = os.path.join(p, e)
            if TEMP.match(e) and os.path.isdir(q) and not os.path.islink(q) and now - os.path.getmtime(q) > TEMP_HOURS * 3600:
                out.append((q, "temporary CI copy"))
    return out


def selftest():
    d = tempfile.mkdtemp()
    try:
        ws = os.path.join(d, "ws"); os.makedirs(ws)
        conn = sqlite3.connect(":memory:")
        conn.execute("create table tasks(id text, status text)")
        conn.execute("create table task_events(task_id text, created_at real)")
        now = time.time()
        for tid, st, age in (("t_done", "done", 10), ("t_new", "done", 1), ("t_run", "running", 30), ("t_rdy", "ready", 30)):
            conn.execute("insert into tasks values(?,?)", (tid, st))
            conn.execute("insert into task_events values(?,?)", (tid, now - age * 86400))
            os.makedirs(os.path.join(ws, tid, "ci-flutter-env-1.abc"))
            os.makedirs(os.path.join(ws, tid, "qa-runtime-20261112-0236"))
            os.makedirs(os.path.join(ws, tid, "app"))
            old = now - 2 * 86400
            os.utime(os.path.join(ws, tid, "ci-flutter-env-1.abc"), (old, old))
        got = {(os.path.relpath(p, ws), w.split()[0]) for p, w in plan(conn, ws, now)}
        assert got == {("t_done", "card"), ("t_new/ci-flutter-env-1.abc", "temporary"),
                       ("t_rdy/ci-flutter-env-1.abc", "temporary")}, got
        print("selftest ok")
    finally:
        shutil.rmtree(d)


def main():
    if not os.path.isdir(WS) or not os.path.exists(DB):
        return
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    items = plan(conn, WS, time.time())
    freed = 0
    for p, why in items:
        if "--dry-run" in sys.argv:
            print(f"would remove {p.replace(H, '~')} ({why}, {size(p) / 1e9:.1f} GB)")
            continue
        n = size(p)
        os.system(f"chmod -R u+rwX '{p}' 2>/dev/null")  # tests leave 0700/0500 folders that block removal
        shutil.rmtree(p, ignore_errors=True)
        if not os.path.exists(p):
            freed += n
    if freed:  # removed worktrees leave stale entries in their main checkouts
        for git in glob.glob(f"{H}/work/*/.git") + glob.glob(f"{H}/work/*/*/.git"):
            os.system(f"git -C '{os.path.dirname(git)}' worktree prune >/dev/null 2>&1")
        print(f"{time.strftime('%F %T')} workspace-clean freed {freed / 1e9:.1f} GB ({len(items)} folders)")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
