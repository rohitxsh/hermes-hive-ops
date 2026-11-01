# Team notification-only @here policy

Requested by the owner in #assistant, 2026-11-01.

## Scope

- `platforms.discord.extra.team_notification_here: true` opts each of the nine Team profiles in.
- Interactive exec approvals, clarification questions, slash confirmations and update prompts receive one @here prefix.
- Cron deliveries are identified by trusted `job_id` metadata. An ordinary final reply's `notify` flag alone does not broadcast.
- Agent-authored notifications can opt in with a leading standalone @here. Quoted or embedded mentions do not opt in. Streaming edits and overflow continuations sanitize their body as well.
- The client-wide `_build_allowed_mentions` safe defaults, approval allowlists/checks, role gates and timeouts remain unchanged. The separate direct-REST Kanban activity feed remains unpinged: it never targeted the owner and is not an approval alert.

## Safety

Discord has no separate allowed-mentions switch for @here: its `everyone` flag also permits @everyone. The notification-only send override therefore neutralizes every body occurrence of both broadcast strings, prefixes one @here, and disables user/role/reply-author mentions. Prefix removal covers the old the owner mention. Large reports remain chunked without content loss. Interactive content budgets reserve the prefix.

## Verification

`test_team_notification_here.py` runs with stdlib unittest and the actual managed Discord SDK; no pytest install is needed. Fourteen tests passed, covering notification scope/default off, body sanitization, cron and ordinary final replies, approval allowlist preservation, clarification, long prompts, forum posts, streaming edits and overflow. Tests exercised real adapter methods with mocked network channels, not a live Discord send. Guild permissions returned by Discord include MENTION_EVERYONE; channel-specific effective permission/push reception remains unverified.

Run with the active managed interpreter and `PYTHONPATH=~/.hermes/hermes-agent`.

## Activation and rollback

The already-running gateway needs a graceful idle restart to load adapter code/config. New source/SOUL instructions do not retroactively alter a running model turn.

Adapter prechange backup: `adapter.py.bak-2026-11-01-161357-here-notify`.
Nine config backups use `.bak-2026-11-01-161357-here-notify`.
Notifier/header/nine SOUL backups use `.bak-2026-11-01-160912-here-notify`.

`team-notification-here.patch` is generated against the prechange adapter, retaining previous local patches. After an upstream update, review and `git apply --check` before reapplying it. For rollback, reverse only this patch or restore its adapter backup if no subsequent changes; restore only the changed config field and notifier/header/SOUL policy, preserving newer edits. Queue the documented graceful idle restart. Do not restore scheduler or approval queue/state.

A successful local regression run or persisted configuration is not proof of a delivered channel ping. Report live delivery separately.
