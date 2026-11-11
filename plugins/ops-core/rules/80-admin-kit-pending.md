---
profiles: default
---
- When you patch an installed tool, plugin or Hermes patch script that also lives in the hive-ops kit (tools/, plugins/, patches/, setup/), add a line to HANDOFF.md starting "kit pending:", naming the file and the change in one sentence. The workstation admin merges it into the kit (with the privacy scan) and removes the line. Otherwise the next kit deploy overwrites your fix.
- When a reported issue starts `admin: reassign t_XXXXXXXX to <profile>` or `admin: retitle t_XXXXXXXX to "<title>"` (card workers can't change the board themselves), apply it straight away with `hermes kanban reassign` or `hermes kanban edit --title`, add a one-line comment on the card, and resolve the issue. Check that the profile exists and the card isn't done; anything else in the request goes through your normal issue handling.
