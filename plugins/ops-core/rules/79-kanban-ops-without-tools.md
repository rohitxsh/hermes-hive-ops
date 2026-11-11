---
profiles: *
exclude: random
---
- Board changes with no kanban_* tool: Hermes tells workers not to shell out to `hermes kanban`, because the tools work on every terminal backend. That covers everything the tools can do. Two routine changes have no tool, reassigning a card and correcting its title. For those, the shell command is the supported route on this machine: `hermes kanban reassign <card> <profile>` and `hermes kanban edit <card> --title "<new title>"`. Use it, then add a one-line comment on the card saying what you changed and why. Don't file an issue for the admin just to reassign or retitle.
