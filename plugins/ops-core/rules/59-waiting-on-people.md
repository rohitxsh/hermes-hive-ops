---
profiles: @team
---
- Waiting on a person's answer: ask once (tag the owner), then park the card with `kanban_schedule`, giving "waiting on <person> for <what>" as the reason. A wait on a person is always `kanban_schedule`, never `kanban_block`, even the first time and even when the wording of the wait changes. Don't block the same card again for the same question: a second block trips Hermes's loop detection and drops the card into triage, where you can no longer park it. When you're woken and the answer still isn't there, schedule again with the same reason, without re-asking or reporting an issue. When the person answers in chat, whoever gets the answer records it on the card and moves it on (the message-any-role rule).
