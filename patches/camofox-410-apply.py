#!/usr/bin/python3
"""Local Hermes patch (vm-a assistant's diagnosis on issue cb6ab3, applied 2026-10-31 at the owner's OK): Camofox answers
HTTP 410 Gone for a tab it destroyed after the idle timeout, but Hermes's navigate only recreated the tab on 404, so a run
stayed stuck on the dead tab and every later site failed. Treat 410 like 404. Idempotent; `--check` only reports.
Lives in ~/agents/src/hermes-local-patches/; re-run after `hermes update` if the self-check says it's missing, then
restart the gateway when idle."""
import shutil
import sys
from pathlib import Path

F = Path.home() / ".hermes/hermes-agent/tools/browser_camofox.py"
TAG = ".bak-2026-10-31-camofox410"
MARK = "local patch (2026-10-31): camofox 410"
OLD = ("            if e.response is None or e.response.status_code != 404:\n"
       "                raise\n"
       "            logger.warning(\"Camofox tab %s returned 404 — tab was garbage collected. Creating a fresh tab.\",\n")
NEW = (f"            # {MARK}: 410 Gone is a tab destroyed after the idle timeout; recreate it like a 404\n"
       "            if e.response is None or e.response.status_code not in (404, 410):\n"
       "                raise\n"
       "            logger.warning(\"Camofox tab %s returned %s — tab is gone. Creating a fresh tab.\",\n")
s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    print("ok" if MARK in s else "missing")
    sys.exit(0 if MARK in s else 1)
if MARK not in s:
    assert s.count(OLD) == 1, "anchor not found once; upstream changed, patch by hand"
    s = s.replace(OLD, NEW)
    # the log call gained a %s for the status code: pass it
    old_args = "                           session[\"tab_id\"])\n            session[\"tab_id\"] = None\n"
    assert s.count(old_args) == 1, "log args anchor"
    s = s.replace(old_args, "                           session[\"tab_id\"], e.response.status_code)\n            session[\"tab_id\"] = None\n")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
compile(F.read_text(encoding="utf-8"), str(F), "exec")
print("ok")
