## Usage limits
<!-- locked-ok -->
- Model quota is shared by every agent on this machine. Before scheduled or autonomous work, run `quota-status --gate`: "paused" means stop and reply [SILENT]; "wrap up" means finish or checkpoint the current step and start nothing new. `quota-status` shows usage when someone asks.
- Also check it before starting background subagents (`delegate_task`) or another long run from chat: on "wrap up" or "paused", say so in one line with the reset time and do the work after the reset (or inline, if it is small). A fan-out that hits the limit fails every subagent and floods the chat with failure notices.
- If you hit a usage or rate limit, stop instead of retrying in a loop, post one short note with the reset time if someone is waiting, and carry on after the reset. Don't create extra jobs to work around a limit.
- Keep the conversation small: batch work, don't re-read big files or repeat searches, save large tool output to a file and read back only what you need. Long chats are compressed automatically.
