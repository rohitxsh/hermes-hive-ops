## Avoiding loops
<!-- locked-ok -->
- If a read-only call (a skill, a file, a search) comes back as identical to an earlier result, or is blocked as repeated, don't make it again: its content was probably compacted out of your context. Read the file directly instead (`read_file` on the skill's SKILL.md path, which `skills_list` shows, or on the document itself) or continue from your notes, and carry on with the task.
- Don't repeat a call that failed the same way twice: change the approach, or report the blocker.
- In a Kanban task, never end a run without `kanban_complete`, `kanban_block` or `kanban_request_review`. If you're stuck, block the task with the reason and what would unblock it, rather than stopping silently.
