---
profiles: *-dev
---
- Cross-review every code PR by the other model before it goes to QA (or, where there is no QA step, before you merge it). Run it in the PR's worktree in the background, like a coding run, and read the output file when it finishes:
  - Claude Code wrote the code: `codex review --base origin/<default branch> --title "<one line: the issue>" > ~/.local/state/claude-runs/<repo>-pr-<N>-review.txt 2>&1` (Codex defaults to gpt-6.1-sol at high reasoning; Codex CLI 0.167+ refuses a review prompt together with `--base`, so the issue goes in `--title` and the acceptance criteria are checked by QA).
  - Codex wrote the code: `claude -p "Review the changes on this branch against origin/<default branch> as a strict senior reviewer: correctness bugs, security, edge cases, missing tests, needless complexity. Must-fix findings first, each with file:line; skip style nits. Do not edit files." --model claude-opus-5-5 --effort high --permission-mode plan --output-format json > ~/.local/state/claude-runs/<repo>-pr-<N>-review.json 2>&1`.
- Send the must-fix findings back to the same coding session as rework (one round; QA judges whatever is left). Post the rest as one PR comment headed "Cross-review (<model>)", then hand the PR on as usual. QA still reads the whole diff and decides; the cross-review is input, not a pass. Skip it for docs-only and one-line changes.
