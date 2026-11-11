---
profiles: default
---
- When you patch an installed tool, plugin or Hermes patch script that also lives in the hive-ops kit (tools/, plugins/, patches/, setup/), add a line to HANDOFF.md starting "kit pending:", naming the file and the change in one sentence. The workstation admin merges it into the kit (with the privacy scan) and removes the line. Otherwise the next kit deploy overwrites your fix.
