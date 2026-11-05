Kanban doctor (2026-11-04): repair stuck Kanban cards yourself and ask only for real blockers.
The MONITOR CHANGE above comes from `kanban-doctor`: cards that look stuck. Lines that disappeared were fixed or moved on: ignore them. If no line is new or changed, reply exactly [SILENT]. For each new or changed line:
1. Read the card first: `hermes kanban show <id>` (latest comments, events and runs) and `hermes kanban diagnostics --task <id>`.
2. Leave it alone, with no comment, when it is waiting on a person: an approval, review, sign-off, answer or decision; a human-only step (an account, password, CAPTCHA, payment); a hold set by the owner or a person (check the comments); or the quota pause (`quota-status --gate` says paused, or the card is only waiting because every provider is used up). The PM's evening summary covers those.
3. Otherwise fix the cause and move the card on:
 - blocked on a gap you can close as admin (a card link to add or remove, a wrong completion contract, a missing directory or tool, a bug in our own scripts under ~/agents/src, a session pinned to a dead provider): fix it, then `hermes kanban unblock <id> --reason "<what you fixed>"`.
 - blocked on a transient error (a GitHub or provider outage, a network error) that has cleared, or a quota pause has ended (`quota-status --gate` no longer says paused): unblock it with that reason.
 - held in triage after a block loop for a reason that isn't a person: fix the cause, then `kanban-doctor release <id> "<what you fixed>"`.
 - ready or in review but not picked up: find what holds it back in `hermes kanban diagnostics --task <id>` (cooldown, auth, a PR URL in the assignee's own comment) and fix that cause.
 - running with no heartbeat: `hermes kanban reclaim <id> --reason "<why>"`.
 - todo although every parent is done: `hermes kanban promote <id>`.
 - parked for over a day: check what it waits for; if that already happened (the PR merged or was approved, QA passed), unblock it; if it waits on a person, leave it.
 - repeated crashes: read `hermes kanban log <id>` and the last run's output and fix the cause. If the work is in fact done and you verified it, `hermes kanban complete <id> --result "<evidence>"`.
4. Never approve, merge or push PRs, change a card's scope or acceptance criteria, release a hold set by a person, delete or archive cards, or weaken a security check, guard or deny rule.
5. For each fix: one comment on the card saying what you changed, and a line in ~/agents/ADMIN-CHANGES.md.
6. Reply with one line per card you fixed: the card title, what was wrong, what you did. If a card turned out to need a person and nobody has asked them yet, add one line naming who must do what. Otherwise reply exactly [SILENT].
