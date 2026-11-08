---
profiles: *-dev *-qa *-devops *-architect
---
- Before you start a Claude Code or Codex run, size the work and pass the model and thinking level explicitly (Claude Code: `claude -p … --model <model> --effort <level>`; Codex: `codex exec -m <model> -c model_reasoning_effort=<level> …`). Use only this table, the current model lineup:
  | Size | When | Codex | Claude Code |
  |---|---|---|---|
  | small | mechanical edits, renames, formatting, dependency bumps, docs, a failing test whose cause is already known | `gpt-6.1-terra`, `low` | `claude-sonnet-5-5`, `low` |
  | standard (default) | a normal feature or bug fix inside one area, with its tests | `gpt-6.1-sol`, `medium` | `claude-sonnet-5-5`, `high` |
  | complex | changes across modules or to the architecture, concurrency, security, auth, permissions or RLS, database migrations, money or deleting data, a bug that survived one attempt | `gpt-6.1-sol`, `xhigh` | `claude-opus-5-5`, `high` |
  | review | cross-review or QA reading of a diff | `gpt-6.1-sol`, `high` | `claude-opus-5-5`, `high` |
- Size by the riskiest part of the change, not its length; when unsure, use standard. A run that fails its checks or QA twice moves up one size; never move down on a retry. No other models (older gpt-6 or gpt-5.6, gpt-6-astra, Claude Fable or 4.x) unless the owner asks for one.
- Name the size and why in the first line of the run's prompt file and in the PR description (e.g. "Run: complex — RLS policy change, gpt-6.1-sol xhigh"), so reviews can see whether the choice fit.
