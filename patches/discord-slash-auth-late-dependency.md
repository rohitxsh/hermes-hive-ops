# Discord slash authorization: late optional dependency

Approved by the owner as `c55300: option 1`, 2026-10-28. Scope: slash authorization only, not the separate media-upload issue 01f738.

## Cause and change

The adapter loads its optional Discord dependency lazily. The slash-auth mixin formerly imported discord at module load, caught ImportError, and cached None permanently. After the adapter loaded discord.py, slash authorization could still dereference None.DMChannel. Resolve discord in _evaluate_slash_authorization instead; if unavailable, reject authorization with `discord.py unavailable`. Leave all user, role, guild, channel, ignored-channel, thread, DM and DM-scope checks unchanged.

Patch: `discord-slash-auth-late-dependency.patch` in this directory. It contains the production change and new `tests/gateway/test_discord_slash_auth_dependencies.py` regressions.

## Verification before restart

- Original slash-auth/import baseline: 20 passed.
- New regression file against the saved original: seven failures reproduced the cached-None crash/fail-closed problem. Against the fix: seven pass.
- Ten-file authorization/import/slash regression selection: 88 passed in 8.92 s on the final run. Includes dependency regressions, existing slash auth, imports, component auth, role/DM scope, slash commands, bot bypass, voice role grants, admission/thread exemption and username allowlist reload.
- Wider channel-controls selection has four failures also reproduced against the unmodified original; not changed by this patch.
- Offline smoke using the gateway's installed discord.py 2.7.1 and a real discord.Interaction for /retry after simulated delayed dependency availability: authorized user accepted, wrong user and ignored channel rejected. No Discord command dispatched and no network calls made. This does not claim a live Discord invocation after restart.
- git diff --check, reverse-apply check, active service and VM agent-health.sh passed before the graceful restart was queued.

## Reapply and undo

Run from `~/.hermes/hermes-agent`. After an update, inspect whether upstream already has the equivalent fix; do not blindly overwrite newer source.

- Reapply: `git apply --check ~/agents/src/hermes-local-patches/discord-slash-auth-late-dependency.patch`, then the same command without `--check`, then run the regressions.
- Undo: `git apply --reverse --check ~/agents/src/hermes-local-patches/discord-slash-auth-late-dependency.patch`, then the same command without `--check`. This restores production code and removes the added regression file, leaving unrelated edits alone.
- Alternate production-only rollback: restore `plugins/platforms/discord/adapter_slash_auth.py.bak-2026-10-28` over the corresponding .py file. Leave the regression file for diagnosis if useful.
- Restart gracefully after applying or undoing, using `sudo systemd-run --unit hermes-restart-idle-$(date +%s) --collect ~/.local/bin/hermes-restart-idle`. Never interrupt active turns with a direct service restart.

## Test environment

Scratch pytest dependencies were used rather than modifying the gateway's managed environment. Use scratch HOME and HERMES_HOME to respect the test home-I/O guard. Scratch files are disposable; the repository regression and this reapply patch are durable. Verify an actual Discord /retry after reconnect; the issue digest reopens recurring errors automatically.
