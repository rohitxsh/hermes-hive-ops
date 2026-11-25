#!/usr/bin/python3
"""Local Hermes patch (2026-11-23): keep provider-plugin snapshots out of the pruned scratch folder.

Why: providers/plugin_reload.py imports each provider plugin from a frozen copy made with tempfile.mkdtemp. Here
TMPDIR is ~/.hermes/cache/scratch, whose hourly prune deletes entries idle for 24 h. A long-running gateway then
lost the copy of the Claude provider plugin; a profile that had not yet imported the plugin's lazy submodule
(`directsdk`) failed with ModuleNotFoundError and its Claude fallback reported "provider not configured" (seen
on two machines, 2026-11-22/23). The snapshot root now lives in $HERMES_HOME/cache/provider-plugins/, named with the owning pid; each
new root removes siblings whose pid is gone (crashed processes skip atexit). Behaviour is otherwise unchanged.
Idempotent; `--check` only reports. Re-run after `hermes update`. Upstream bug: snapshots should not use TMPDIR.
"""
import shutil
import sys
from pathlib import Path

F = Path.home() / ".hermes/hermes-agent/providers/plugin_reload.py"
TAG = ".bak-2026-11-23-provider-snapshot"
MARK = "local patch (2026-11-23): provider snapshots outside the pruned scratch dir"
OLD = ('        if _snapshot_root is None:\n'
       '            _snapshot_root = Path(tempfile.mkdtemp(prefix="hermes-provider-plugins-"))\n'
       '            atexit.register(shutil.rmtree, _snapshot_root, True)\n')
NEW = (f'        if _snapshot_root is None:\n'
       f'            # {MARK}\n'
       '            _snapshot_root = _new_snapshot_root()\n'
       '            atexit.register(shutil.rmtree, _snapshot_root, True)\n')
HELPER_ANCHOR = 'def _snapshot(plugin_dir: Path, module_name: str) -> Path:\n'
HELPER = (f'# {MARK}\n'
          'def _new_snapshot_root() -> Path:\n'
          '    """A per-process snapshot root under $HERMES_HOME/cache/provider-plugins (never TMPDIR: a scratch\n'
          '    pruner deleting it under a live process breaks lazy imports). Roots of dead processes are removed."""\n'
          '    try:\n'
          '        from hermes_constants import get_hermes_home\n'
          '        base = Path(get_hermes_home()) / "cache" / "provider-plugins"\n'
          '        base.mkdir(parents=True, exist_ok=True)\n'
          '    except Exception:\n'
          '        return Path(tempfile.mkdtemp(prefix="hermes-provider-plugins-"))\n'
          '    for old in base.glob("p*-*"):\n'
          '        try:\n'
          '            pid = int(old.name[1:].split("-", 1)[0])\n'
          '        except ValueError:\n'
          '            continue\n'
          '        if pid == os.getpid():\n'
          '            continue\n'
          '        try:\n'
          '            os.kill(pid, 0)\n'
          '        except ProcessLookupError:\n'
          '            shutil.rmtree(old, ignore_errors=True)\n'
          '        except OSError:\n'
          '            pass\n'
          '    return Path(tempfile.mkdtemp(prefix=f"p{os.getpid()}-", dir=base))\n'
          '\n\n')

s = F.read_text(encoding="utf-8")
done = MARK in s
if "--check" in sys.argv:
    print("ok" if done else "missing")
    sys.exit(0 if done else 1)
if not done:
    assert s.count(OLD) == 1, "snapshot-root anchor not found once; upstream changed, patch by hand"
    assert s.count(HELPER_ANCHOR) == 1, "_snapshot anchor not found once"
    assert "import os\n" in s and "import tempfile\n" in s, "imports this patch uses are missing"
    s = s.replace(OLD, NEW).replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR)
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
