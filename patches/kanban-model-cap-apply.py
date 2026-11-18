#!/usr/bin/python3
"""Local Hermes patch (2026-11-18): cap how many Kanban workers run at once on the same pinned model.

Why: after the Claude weekly reset five Mythos-pinned review cards started together; the shared 5-hour window was
full in 45 minutes and all of them crashed mid-run ("waiting for model response"), then sat blocked. The dispatcher
only knows a global cap and a per-profile cap. With this patch, `kanban.max_in_progress_per_model` in the main
config (a map of model name -> number, e.g. {claude-mythos-5-2: 1}) makes the dispatcher leave a ready card in the
queue while that many cards pinned to the same model (`model_override`) are running. It is counted like the
per-profile cap ("busy, retry later", not "stuck") and read on every tick, so a config change needs no restart.
No map, or a model not in it: unchanged behaviour.
Idempotent; `--check` only reports; `--test` runs a self-test on a temporary board with Hermes's venv python.
Re-run after `hermes update`."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F = ROOT / "hermes_cli/kanban_db_dispatch.py"
TAG = ".bak-2026-11-18-model-cap"
MARK = "local patch (2026-11-18): per-model running cap"
OLD = ('            result.skipped_per_profile_capped.append((task_id, assignee, current))\n'
       '            return False\n'
       '    guard_reason = check_respawn_guard(conn, task_id, lane=lane)\n')
NEW = ('            result.skipped_per_profile_capped.append((task_id, assignee, current))\n'
       '            return False\n'
       f'    # {MARK}: kanban.max_in_progress_per_model\n'
       '    model_running = _model_cap_reached(conn, task_id)\n'
       '    if model_running is not None:\n'
       '        result.skipped_per_profile_capped.append((task_id, assignee, model_running))\n'
       '        return False\n'
       '    guard_reason = check_respawn_guard(conn, task_id, lane=lane)\n')
HELPER = f'''

def _model_cap_reached(conn, task_id, caps=None):
    """{MARK}: running count of the task's pinned model when it is at its
    kanban.max_in_progress_per_model cap, else None."""
    if caps is None:
        try:
            from hermes_cli.config import load_config
            caps = (load_config().get("kanban") or {{}}).get("max_in_progress_per_model") or {{}}
        except Exception:
            return None
    if not isinstance(caps, dict) or not caps:
        return None
    row = conn.execute("SELECT model_override FROM tasks WHERE id = ?", (task_id,)).fetchone()
    model = row[0] if row else None
    cap = caps.get(model) if model else None
    if not isinstance(cap, int) or cap < 1:
        return None
    n = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running' AND model_override = ?",
                     (model,)).fetchone()[0]
    return int(n) if n >= cap else None
'''


def selftest():
    home = tempfile.mkdtemp(prefix="kb-modelcap-")
    os.environ["HERMES_HOME"] = home
    sys.path.insert(0, str(ROOT))
    from hermes_cli import kanban_db as kb
    from hermes_cli import kanban_db_connect as kbc
    from hermes_cli import kanban_db_dispatch as kd
    try:
        with kbc.connect() as conn:
            a = kb.create_task(conn, title="a", assignee="qa", model_override="m-scarce")
            b = kb.create_task(conn, title="b", assignee="qa", model_override="m-scarce")
            c = kb.create_task(conn, title="c", assignee="qa", model_override="m-other")
            d = kb.create_task(conn, title="d", assignee="qa")
            caps = {"m-scarce": 1}
            assert kd._model_cap_reached(conn, b, caps) is None            # nothing running yet
            assert kb.claim_task(conn, a) is not None
            assert kd._model_cap_reached(conn, b, caps) == 1               # cap reached: b waits
            assert kd._model_cap_reached(conn, c, caps) is None            # other model unaffected
            assert kd._model_cap_reached(conn, d, caps) is None            # unpinned unaffected
            assert kd._model_cap_reached(conn, b, {"m-scarce": 2}) is None
            assert kd._model_cap_reached(conn, b, {}) is None
            assert kd._model_cap_reached(conn, b, {"m-scarce": 0}) is None
        print("selftest ok 7 cases")
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
    assert s.count(OLD) == 1, "kanban_db_dispatch per-profile cap anchor not found once; upstream changed, patch by hand"
    s = s.replace(OLD, NEW).rstrip("\n") + "\n" + HELPER
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
