---
profiles: *
exclude: random
---
- Board changes with no kanban_* tool: a card worker can't reassign or retitle a card. There is no tool for it, and Hermes fences `hermes kanban` writes from a worker's own terminal and its sub-agents alike ("cannot mutate Kanban tasks via the CLI"), so don't try the shell. To hand work back after a review, use `kanban_request_changes`. For any other reassign or retitle, file one `report-issue` whose text starts exactly `admin: reassign t_XXXXXXXX to <profile>` or `admin: retitle t_XXXXXXXX to "<new title>"`, with the reason after it, and carry on with other work; the admin applies it. Only sessions outside a card worker (the assistant, or a chat session) can make these changes directly.
