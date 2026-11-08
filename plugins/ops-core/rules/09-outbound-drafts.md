---
profiles: *
exclude: random
---
- In a run nobody is watching (a scheduled job, a Kanban worker, auto mode), don't email or message anyone outside your team yourself: save the exact send command as a draft with `outbox draft --to "<who>" --summary "<what and why, one line>" -- <command>`. The owner gets it in the admin channel and sends it with one reply. Posting in your own team's channels and threads, and on your own repositories' PRs and issues, is not outbound and needs no draft. In a live chat, send when the person you're talking to asks.
