#!/usr/bin/python3
"""Local Hermes patch (2026-11-05): the respawn guard holds a card ("blocker_auth") whenever its last_failure_error looks
like a quota or auth error. That text is left behind by an older rate-limited run and isn't cleared when a later run
ends normally (for example a QA verdict that hands the card back for rework), so the card was held forever and the
dispatcher logged "ready queue non-empty ... 0 workers spawned" all day. The guard now ignores that text once the latest
run ended normally (completed, review_requested, blocked or scheduled). Idempotent; `--check` only reports. Lives in
~/agents/src/hermes-local-patches/; re-run after `hermes update` if the self-check says it's missing, then restart the
gateway when idle."""
import shutil
import sys
from pathlib import Path

F = Path.home() / ".hermes/hermes-agent/hermes_cli/kanban_db_dispatch.py"
TAG = ".bak-2026-11-05-staleauth"
MARK = "local patch (2026-11-05): an error left by an older run is stale"
ENDED = '("crashed", "completed", "review_requested", "blocked", "scheduled")'
# one anchor per Hermes version: v0.23.4 added `and not infrastructure`
VARIANTS = [
    ('    if err and latest_outcome != "crashed" and _RESPAWN_BLOCKER_RE.search(err):\n',
     f"    # {MARK} once a later run ended normally\n"
     f'    if err and latest_outcome not in {ENDED} \\\n'
     "            and _RESPAWN_BLOCKER_RE.search(err):\n"),
    ('    if err and latest_outcome != "crashed" and not infrastructure and _RESPAWN_BLOCKER_RE.search(err):\n',
     f"    # {MARK} once a later run ended normally\n"
     f'    if err and latest_outcome not in {ENDED} and not infrastructure \\\n'
     "            and _RESPAWN_BLOCKER_RE.search(err):\n"),
]

s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    print("ok" if MARK in s else "missing")
    sys.exit(0 if MARK in s else 1)
if MARK not in s:
    hit = [(a, b) for a, b in VARIANTS if s.count(a) == 1]
    assert len(hit) == 1, "anchor not found once; upstream changed, patch by hand"
    s = s.replace(*hit[0])
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
