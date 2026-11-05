---
profiles: default
---
- Shared rules are managed in one place. The "Shared rules" block at the end of each SOUL (between the ops-rules markers) is written by the ops-core plugin from rule files: the kit's in `~/.hermes/plugins/ops-core/rules/` and this machine's own in `~/agents/rules/` (front matter names the profiles, as fnmatch patterns). To add or change a rule that applies to several profiles, edit or add a file in `~/agents/rules/`, run `hermes ops-rules apply`, then `hermes ops-rules check` (it must report 0) and log it in ~/agents/ADMIN-CHANGES.md. Never edit that block inside a SOUL by hand: the next apply overwrites it. A change to one role's own text still goes in that SOUL (or its source) as before.
