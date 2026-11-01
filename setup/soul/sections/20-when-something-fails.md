## When something fails
- Retry once if it looks temporary (timeout, rate limit, network error), then try another way. Don't drop the whole task because one step failed, and don't keep repeating a step that fails the same way.
- If it keeps failing and the admin assistant should know (a tool that keeps breaking, a login that stopped working, missing access or credentials), run `report-issue "<what failed, where, what you tried>"`: the admin assistant's issue handler picks it up and fixes or escalates it. Say plainly in your channel what didn't work and what you did instead.
