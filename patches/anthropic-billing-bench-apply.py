#!/usr/bin/python3
"""Local Hermes patch (2026-11-18): Anthropic request-time refresh must not undo credential-pool rotation.

Why: when the Claude credential in use ran out of billing or auth, the pool rotated to another credential, but the
request-time refresh (resolve_anthropic_token -> token_is_blocked) only looked at model-specific cooldowns, so it
handed the exhausted credential back on the next request. Workers then looped on billing errors (thousands of log
lines an hour) until the watchdog interrupted the turn. token_is_blocked now also honours a credential marked dead
and the pool's existing exhausted-until policy. No TTL, routing, fallback or quota change.
Idempotent; `--check` only reports. Re-run after `hermes update`."""
import shutil
import sys
from pathlib import Path

F = Path.home() / ".hermes/hermes-agent/agent/credential_pool_model_cooldowns.py"
TAG = ".bak-2026-11-18-billing-bench"
MARK = "local patch (2026-11-18): honour dead/exhausted credentials in request-time refresh"
OLD = ('        with self._lock:\n'
       '            return any(\n'
       '                entry.runtime_api_key == token and model_cooldown_until(entry, model) is not None\n'
       '                for entry in self._entries\n'
       '            )\n')
NEW = (f'        # {MARK}\n'
       '        from agent.credential_pool import STATUS_DEAD, _exhausted_until\n'
       '        with self._lock:\n'
       '            now = time.time()\n'
       '            sole_credential = self._is_sole_credential()\n'
       '            return any(\n'
       '                entry.runtime_api_key == token and (\n'
       '                    entry.last_status == STATUS_DEAD\n'
       '                    or (_exhausted_until(entry, sole_credential=sole_credential) or 0) > now\n'
       '                    or model_cooldown_until(entry, model) is not None\n'
       '                )\n'
       '                for entry in self._entries\n'
       '            )\n')

s = F.read_text(encoding="utf-8")
# an earlier local install (same method body, no marker) counts as applied
done = MARK in s or ("entry.last_status == STATUS_DEAD\n" in s and "_exhausted_until(entry, sole_credential" in s)
if "--check" in sys.argv:
    print("ok" if done else "missing")
    sys.exit(0 if done else 1)
if not done:
    assert s.count(OLD) == 1, "token_is_blocked anchor not found once; upstream changed, patch by hand"
    assert "import time" in s and "_is_sole_credential" in s, "helpers this patch uses are missing"
    s = s.replace(OLD, NEW)
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
