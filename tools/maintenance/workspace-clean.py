#!/usr/bin/env python3
"""Cleanup of agent work folders that nothing else removes, every 6 hours.

Card workspaces (~/.hermes/kanban/workspaces/<card>) hold worktrees, Flutter test environments and evidence copies;
one VM reached 59 GB and about 1% of disk an hour. Long-lived cards also keep a fresh clone or build per QA or test
round (qa-469-flutter-1828, ci-20261127-2116, ...), and agents leave folders in /tmp and dated worktrees in ~/work.
This removes:
  - the workspace of a card that is done or archived and has had no board event for DONE_DAYS (default 3), and of a
    card that no longer exists;
  - inside any card that is not running: temporary local-CI copies (top-level `ci-*-env-*` and `*.tmp*` directories)
    older than TEMP_HOURS (default 6), and per-run copies (top-level directories whose name carries a date or run
    stamp, four or more digits) untouched for RUN_DAYS (default 2) that are a git checkout or bigger than RUN_MIN_MB
    (default 100), always keeping the card's KEEP_RUNS (default 2) newest. Small dated folders (usually evidence an
    agent may reread), directories with stable names (app, repo, source-repair, ...) and plain files stay;
  - in /tmp: directories this user owns that nothing touched for TMP_DAYS (default 3), except system, tmux, Claude and
    Hermes folders;
  - in ~/work/<project>/ and ~/work/<project>/*-worktrees/: dated git worktrees (a `.git` file, a date in the name)
    untouched for WORK_DAYS (default 7).
A running card is never touched, and nothing a live process has as its working directory is removed. Evidence lives
on the card and in GitHub, and Hermes recreates a worktree when a card reopens. Each run also records disk use in
~/.local/state/disk-samples; `--growth` prints one warning line when / grew by more than GROWTH_GB (default 10) in
the last day (the self-check reports it). Prints one summary line when it freed space; `--dry-run` lists what it
would remove; `--selftest`.
Runs every 6 hours from crontab (`15 */6 * * * python3 ~/agents/src/workspace-clean/workspace-clean.py`).
"""
import glob
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

H = os.path.expanduser("~")
WS = f"{H}/.hermes/kanban/workspaces"
DB = f"{H}/.hermes/kanban.db"
SAMPLES = f"{H}/.local/state/disk-samples"
DONE_DAYS = float(os.environ.get("WORKSPACE_DONE_DAYS", 3))
TEMP_HOURS = float(os.environ.get("WORKSPACE_TEMP_HOURS", 6))
RUN_DAYS = float(os.environ.get("WORKSPACE_RUN_DAYS", 2))
KEEP_RUNS = int(os.environ.get("WORKSPACE_KEEP_RUNS", 2))
RUN_MIN_MB = float(os.environ.get("WORKSPACE_RUN_MIN_MB", 100))
TMP_DAYS = float(os.environ.get("WORKSPACE_TMP_DAYS", 3))
WORK_DAYS = float(os.environ.get("WORKSPACE_WORK_DAYS", 7))
GROWTH_GB = float(os.environ.get("WORKSPACE_GROWTH_GB", 10))
TEMP = re.compile(r"^(ci-[\w.-]+|.*\.tmp[\w.-]*|[\w.-]+-\d{8}-\d{4}\.[A-Za-z0-9]{6})$")  # local-CI runs, mktemp dirs
RUN = re.compile(r"\d{4}")  # a date, time or run number in the name marks a per-run copy
DATED = re.compile(r"20\d{6}")
TMP_KEEP = re.compile(r"^(\.|systemd-|tmux-|snap-|claude|hermes|codex|camofox|pytest-of-|ssh-|pyright|node-compile-cache)")


def size(p):
    total = 0
    for root, _, files in os.walk(p, followlinks=False):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def newest(p, depth=2):
    """Latest mtime of p and its entries down to `depth` levels (cheap: copies are rarely edited deep inside)."""
    best = os.lstat(p).st_mtime
    if depth and os.path.isdir(p) and not os.path.islink(p):
        try:
            for e in os.scandir(p):
                try:
                    best = max(best, newest(e.path, depth - 1) if e.is_dir(follow_symlinks=False) else e.stat(follow_symlinks=False).st_mtime)
                except OSError:
                    pass
        except OSError:
            pass
    return best


def bigger_than(p, limit):
    """True once the files under p pass `limit` bytes (stops walking early)."""
    total = 0
    for root, _, files in os.walk(p, followlinks=False):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
            if total > limit:
                return True
    return False


def disposable(q):
    """A git checkout or a big build/test tree; small folders are usually evidence an agent may reread."""
    if os.path.exists(os.path.join(q, ".git")):
        return True
    try:
        if any(e.is_dir(follow_symlinks=False) and os.path.exists(os.path.join(e.path, ".git")) for e in os.scandir(q)):
            return True
    except OSError:
        return False
    return bigger_than(q, RUN_MIN_MB * 2**20)


def live_cwds():
    out = set()
    for d in glob.glob("/proc/[0-9]*"):
        try:
            out.add(os.readlink(f"{d}/cwd"))
        except OSError:
            pass
    return out


def busy(p, cwds):
    return any(c == p or c.startswith(p + os.sep) for c in cwds)


def plan(conn, ws, now, cwds=frozenset()):
    """[(path, why)] to remove from the card workspaces."""
    out = []
    for d in sorted(os.listdir(ws)):
        p = os.path.join(ws, d)
        if not os.path.isdir(p) or os.path.islink(p):
            continue
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (d,)).fetchone()
        if row is None:
            if now - os.path.getmtime(p) > DONE_DAYS * 86400 and not busy(p, cwds):
                out.append((p, "card no longer exists"))
            continue
        status = row[0]
        if status == "running":
            continue
        last = conn.execute("SELECT MAX(created_at) FROM task_events WHERE task_id = ?", (d,)).fetchone()[0] or 0
        if status in ("done", "archived") and now - float(last) > DONE_DAYS * 86400:
            if not busy(p, cwds):
                out.append((p, f"card {status} {int((now - float(last)) / 86400)} days"))
            continue
        runs = []
        for e in os.listdir(p):
            q = os.path.join(p, e)
            if not os.path.isdir(q) or os.path.islink(q) or busy(q, cwds):
                continue
            if TEMP.match(e):
                if now - os.path.getmtime(q) > TEMP_HOURS * 3600:
                    out.append((q, "temporary CI copy"))
            elif RUN.search(e):
                runs.append((newest(q), q))
        runs.sort(reverse=True)
        for when, q in runs[KEEP_RUNS:]:
            if now - when > RUN_DAYS * 86400 and disposable(q):
                out.append((q, f"per-run copy, untouched {int((now - when) / 86400)} days"))
    return out


def plan_tmp(tmp, now, uid, cwds=frozenset()):
    out = []
    for e in sorted(os.listdir(tmp)):
        q = os.path.join(tmp, e)
        try:
            st = os.lstat(q)
        except OSError:
            continue
        if TMP_KEEP.match(e) or st.st_uid != uid or not os.path.isdir(q) or os.path.islink(q) or busy(q, cwds):
            continue
        when = newest(q, 3)
        if now - when > TMP_DAYS * 86400:
            out.append((q, f"/tmp folder untouched {int((now - when) / 86400)} days"))
    return out


def plan_work(work, now, cwds=frozenset()):
    out = []
    for q in sorted(glob.glob(f"{work}/*/*") + glob.glob(f"{work}/*/*-worktrees/*")):
        e = os.path.basename(q)
        if not DATED.search(e) or not os.path.isfile(os.path.join(q, ".git")) or os.path.islink(q) or busy(q, cwds):
            continue
        when = newest(q)
        if now - when > WORK_DAYS * 86400:
            out.append((q, f"dated worktree untouched {int((now - when) / 86400)} days"))
    return out


def used_bytes(path="/"):
    st = os.statvfs(path)
    return (st.f_blocks - st.f_bfree) * st.f_frsize


def record_sample(now, used, path=SAMPLES):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = open(path).read().splitlines()[-59:] if os.path.exists(path) else []
    with open(path, "w") as fh:
        fh.write("\n".join(lines + [f"{int(now)} {used}"]) + "\n")


def growth(now, used, path=SAMPLES):
    """A warning when / grew by more than GROWTH_GB since the newest sample at least 20 h old, else ''."""
    try:
        rows = [tuple(map(int, l.split())) for l in open(path) if l.strip()]
    except (OSError, ValueError):
        return ""
    old = [r for r in rows if now - r[0] >= 20 * 3600]
    if not old:
        return ""
    t, u = old[-1]
    gb = (used - u) / 1e9
    if gb > GROWTH_GB:
        return (f"disk / grew {gb:.0f} GB in {(now - t) / 3600:.0f} h (now {used / 1e9:.0f} GB used): find the source with "
                f"du -xh --max-depth=2 ~ | sort -rh | head; workspace-clean --dry-run shows what the cleanup would remove")
    return ""


def selftest():
    d = tempfile.mkdtemp()
    try:
        ws = os.path.join(d, "ws"); os.makedirs(ws)
        conn = sqlite3.connect(":memory:")
        conn.execute("create table tasks(id text, status text)")
        conn.execute("create table task_events(task_id text, created_at real)")
        now = time.time()
        old = now - 4 * 86400

        def mk(*parts, age=None):
            q = os.path.join(*parts); os.makedirs(q, exist_ok=True)
            if age is not None:
                os.utime(q, (age, age))
            return q
        for tid, st, age in (("t_done", "done", 10), ("t_new", "done", 1), ("t_run", "running", 30), ("t_rdy", "ready", 30)):
            conn.execute("insert into tasks values(?,?)", (tid, st))
            conn.execute("insert into task_events values(?,?)", (tid, now - age * 86400))
            mk(ws, tid, "ci-flutter-env-1.abc", age=now - 2 * 86400)
            mk(ws, tid, "app", age=old)
        # t_rdy: three old per-run copies (the two newest stay), one fresh one, one busy one
        for name, age in (("qa-r1-20261119-0144", old - 300), ("qa-r2-20261120-0100", old - 200),
                          ("qa-r3-20261121-0100", old - 100), ("qa-469-flutter-1828", now),
                          ("ac6-guard-out-20261114-1528", old - 500)):  # small evidence folder: stays
            q = mk(ws, "t_rdy", name)
            if not name.startswith("ac6"):
                open(os.path.join(q, ".git"), "w").write("gitdir: x\n")
                os.utime(os.path.join(q, ".git"), (age, age))
            os.utime(q, (age, age))
        busy_dir = mk(ws, "t_rdy", "qa-r0-20261118-0100", age=old - 400)
        got = {(os.path.relpath(p, ws), w.split()[0]) for p, w in plan(conn, ws, now, {busy_dir + "/sub"})}
        assert got == {("t_done", "card"), ("t_new/ci-flutter-env-1.abc", "temporary"),
                       ("t_rdy/ci-flutter-env-1.abc", "temporary"), ("t_rdy/qa-r1-20261119-0144", "per-run"),
                       ("t_rdy/qa-r2-20261120-0100", "per-run")}, got
        tmp = mk(d, "tmp")
        mk(tmp, "proj-472", age=old); mk(tmp, "fresh-work"); mk(tmp, "claude-1000", age=old); mk(tmp, "systemd-private-x", age=old)
        assert [os.path.basename(p) for p, _ in plan_tmp(tmp, now, os.getuid())] == ["proj-472"]
        work = mk(d, "work")
        for name, age in (("wt-beta-install-20261109", old - 7 * 86400), ("docs", old - 7 * 86400), ("ci-pr-off-20261124-2342", now)):
            q = mk(work, "proj", name)
            if name != "docs":
                open(os.path.join(q, ".git"), "w").write("gitdir: x\n")
            for x in (q, os.path.join(q, ".git")) if name != "docs" else (q,):
                os.utime(x, (age, age))
        q = mk(work, "proj", "app-worktrees", "issue-20261101-a"); open(os.path.join(q, ".git"), "w").write("gitdir: x\n")
        for x in (q, os.path.join(q, ".git")):
            os.utime(x, (old - 7 * 86400, old - 7 * 86400))
        assert sorted(os.path.basename(p) for p, _ in plan_work(work, now)) == ["issue-20261101-a", "wt-beta-install-20261109"]
        s = os.path.join(d, "samples")
        record_sample(now - 25 * 3600, 100 * 10**9, s); record_sample(now - 2 * 3600, 105 * 10**9, s)
        assert growth(now, 108 * 10**9, s) == "" and growth(now, 115 * 10**9, s).startswith("disk / grew 15 GB")
        print("selftest ok")
    finally:
        shutil.rmtree(d)


def free_bytes():
    st = os.statvfs(WS)
    return st.f_bavail * st.f_frsize


def main():
    if "--growth" in sys.argv:
        msg = growth(time.time(), used_bytes())
        if msg:
            print(msg)
        return
    if not os.path.isdir(WS) or not os.path.exists(DB):
        return
    # Deleting tens of GB at full speed stalled the gateway's event loop for >10 s and it lost its running workers
    # (19 Nov): run at idle I/O and CPU priority, one folder at a time with a pause between, and don't walk sizes.
    try:
        os.nice(19)
        subprocess.run(["ionice", "-c3", "-p", str(os.getpid())], capture_output=True)
    except OSError:
        pass
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    now, cwds = time.time(), live_cwds()
    items = plan(conn, WS, now, cwds) + plan_tmp("/tmp", now, os.getuid(), cwds) + plan_work(f"{H}/work", now, cwds)
    before, removed = free_bytes(), 0
    for p, why in items:
        if "--dry-run" in sys.argv:
            print(f"would remove {p.replace(H, '~')} ({why}, {size(p) / 1e9:.1f} GB)")
            continue
        subprocess.run(["chmod", "-R", "u+rwX", p], capture_output=True)  # tests leave 0700/0500 folders
        shutil.rmtree(p, ignore_errors=True)
        removed += not os.path.exists(p)
        time.sleep(2)
    freed = free_bytes() - before
    if removed:  # removed worktrees leave stale entries in their main checkouts
        for git in glob.glob(f"{H}/work/*/.git") + glob.glob(f"{H}/work/*/*/.git"):
            subprocess.run(["git", "-C", os.path.dirname(git), "worktree", "prune"], capture_output=True)
        print(f"{time.strftime('%F %T')} workspace-clean freed {max(freed, 0) / 1e9:.1f} GB ({removed} folders)")
    if "--dry-run" not in sys.argv:
        record_sample(time.time(), used_bytes())


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
