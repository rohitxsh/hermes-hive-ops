---
profiles: *-dev *-architect
---
- Keep code simple enough for agents to change safely: a new or changed function stays under cyclomatic complexity 15. Turn on the repo's own linter check where it exists (Python: ruff `C901` with `max-complexity = 15`; JS/TS: ESLint `complexity: ["error", 15]`; Dart: split long methods, there is no built-in rule) and split code that crosses it instead of adding exceptions.
- In large repos, give each major folder (a feature module, the database or backend folder, the app shell) a short AGENTS.md: what lives there, its conventions, how to test it, what not to touch. Keep each under about 60 lines and current with the code. Hermes and Codex read nested AGENTS.md files; for Claude Code add a CLAUDE.md beside it containing `@AGENTS.md`. The architect writes them when a folder first matters; dev updates them in the same PR as the change they describe.
