---
profiles: *
exclude: random
---
- Token discipline: a document over about 30k characters (architecture docs, reviews, long specs, logs) is never read whole: search for the part you need, then read just that section with an offset and limit. Don't re-read a file you already read in this session unless it changed, and don't load a skill again in the same session unless your context was compressed since; work from what you have. Keep tool output small: filter command and API output (grep, head/tail, `--json` with only the fields you need, `--limit`) instead of printing it whole, and don't paste long output back into your reply.
