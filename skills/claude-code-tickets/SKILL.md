---
name: claude-code-tickets
description: Coding workflow for this profile's repo. Plan with the user, write each coding task as a GitHub issue, then hand the tickets to Claude Code CLI (Codex CLI when Claude Code hits a usage limit) one at a time, review its pull request, merge, and move on. Use whenever code needs to be written or changed.
---

# Tickets → Claude Code

You (Hermes) plan with the user, write the tickets, hand them off, review and merge. **Claude Code writes the code.** If Claude Code reports a usage limit or a login error, **Codex CLI** (`codex`, the ChatGPT login, `gpt-6.1-sol` at high) takes the ticket instead; one CLI per ticket, back to Claude Code after its reset. Don't write or edit application code yourself. Small non-code edits (ticket text, notes in `docs/`) are fine.

The repo, its checkout and the merge rules are in your SOUL. Git and `gh` are already signed in for that repo.

## 1. Write the tickets

After you and the user agree on a plan, create one GitHub issue per coding task, each small enough for one pull request (`gh issue create`). Each issue holds:

- **Goal:** one or two sentences.
- **Context:** what exists, the relevant files, links.
- **Acceptance criteria:** a checklist the PR must satisfy.
- **Checks:** the commands that must pass, for example `flutter analyze && flutter test`.
- **Out of scope:** what not to touch.
- `Depends on #N` lines where order matters.

If your SOUL names a GitHub Project board, add each ticket to it (`gh project item-add <number> --owner example --url <issue-url>`) and keep its Status current as the ticket moves. Label each new ticket `ready`. The labels are `ready`, `in-progress`, `review` and `blocked`; create any that are missing once with `gh label create`. Tell the user how many tickets were created and in what order they will run, with links.

## 2. Hand off one ticket at a time

Before starting a Claude Code run, check `quota-status --gate --claude-code`. If it says paused (Claude is used up, or too close to the limit to start a run, or Claude is at the quota cap that applies to this profile), check `quota-status --gate` (the Codex side); if that says ok, run the ticket with Codex CLI instead. If both are paused, don't start; say when it will be possible.

Take the lowest-numbered `ready` issue whose `Depends on` issues are all closed. Never run two Claude Code tickets at once.

1. Label it: `gh issue edit N --remove-label ready --add-label in-progress`.
2. Make a worktree on a fresh branch from the default branch:
   `git -C <repo> fetch -q origin && git -C <repo> worktree add <repo>-worktrees/issue-N -b issue-N-<short-slug> origin/main`.
   If the repo has no commits yet, the first ticket (the project skeleton) runs in the main checkout on `main`. Claude Code commits and pushes `main` directly, because there is nothing to open a PR against yet.
   Otherwise open the PR as a draft now, before any code is written, so the work is visible from the start:
   `git -C <worktree> commit -q --allow-empty -m "Start #N: <issue title>" && git -C <worktree> push -q -u origin issue-N-<slug> && gh pr create --draft --head issue-N-<slug> --title "<issue title>" --body "Closes #N"`.
   Every later push updates this PR; it stays a draft until it is ready for approval and merging.
3. Write the handoff prompt to `~/.local/state/claude-runs/<repo>-issue-N.prompt`. It contains:
   - the full issue text (`gh issue view N`)
   - "Work only in this directory, on branch `issue-N-<slug>`."
   - "Run the checks listed in the ticket and fix failures before finishing. No Android/Gradle builds unless the ticket asks for one."
   - "Tests: before writing any, read ~/agents/shared-skills-team/software-development/test-first/SKILL.md and follow it: test at the seams the issue's Testing decisions names, one failing test then the code, no tests tied to internals or passing by construction, no near-duplicate cases."
   - "PR description: write and keep it in the format of ~/agents/shared-skills-team/software-development/pr-body/SKILL.md (summary with a small visual, before/after evidence, merge danger). It replaces any other description format in this prompt."
   - "Commit with clear messages and push the branch. Its draft pull request already exists: don't open another one and don't mark it ready. Keep its description current with `gh pr edit --body-file`: two or three plain sentences first (what this changes for the people using the product, and anything someone needs to do), then the full technical description (what changed and why, how it was tested, risks and open points), ending with `Closes #N`."
   - "Finish with a short summary: what changed, which checks ran and their results, anything left undone."
4. Start Claude Code **in the background**. A coding run outlasts the foreground tool time limit:
   `terminal(command="cd <worktree> && claude -p \"$(cat ~/.local/state/claude-runs/<repo>-issue-N.prompt)\" --dangerously-skip-permissions --model <model> --effort <level> --max-turns 200 --output-format json > ~/.local/state/claude-runs/<repo>-issue-N.json 2>&1", background=true, notify_on_complete=true)`
   Codex CLI (fallback): `terminal(command="cd <worktree> && codex exec -m <model> -c model_reasoning_effort=<level> --dangerously-bypass-approvals-and-sandbox --json -o ~/.local/state/claude-runs/<repo>-issue-N.summary.txt - < ~/.local/state/claude-runs/<repo>-issue-N.prompt > ~/.local/state/claude-runs/<repo>-issue-N.jsonl 2>&1", background=true, notify_on_complete=true)` (full access, like Claude Code's skip-permissions)
   Pick `<model>` and `<level>` from the coding-run table in your Shared rules (small / standard / complex / review) and name the size in the prompt file's first line.
5. Tell the user in one line: "Handed #N to <Claude Code|Codex>: <title>."
6. Wait for the completion notice. Don't poll in a loop, and don't start anything else in the repo meanwhile.

## Requesting the owner's review

In a QA-gated pipeline, keep the PR draft through the dev checks and independent QA; only QA marks it ready (`gh pr ready <pr>`) after full acceptance. Outside such a pipeline, mark it ready when all applicable checks have passed. A review request never bypasses the QA gate.

When a PR needs the owner (your SOUL says so, for example a `human-signoff` PR, or they asked to see it):
1. `gh pr edit <pr> --add-assignee example --add-label needs-owner-review`
2. `gh pr edit <pr> --add-reviewer example`. GitHub refuses this while PRs are opened from the owner's own account ("Review cannot be requested from pull request author"); that's expected, so carry on.
3. Post in your Discord channel: the PR link, why it needs them, and what to check.
4. Don't merge until they approve: an approving review on GitHub, or "approved" / "merge it" from them in chat. Then remove the `needs-owner-review` label and merge as usual.

## 3. Review, then merge or send back

When the run finishes, read the JSON: `is_error`, `result` (Claude Code's summary), `session_id`, `num_turns`, `total_cost_usd`. Codex: the summary file, and the `thread.started` event in the .jsonl for its session id; a run that ended with an `error` or `turn.failed` event failed.

1. Find the PR: `gh pr list --head issue-N-<slug> --json number,url`. Read `gh pr view`, skim `gh pr diff`, and check `gh pr checks` if CI exists.
2. Run the ticket's checks yourself in the worktree.
3. **If it meets every acceptance criterion and the checks pass:** label `review` → `gh pr ready <pr>` (when your SOUL hands PRs to QA first, QA does this) → merge with `gh pr merge <pr> --squash --delete-branch` (the issue closes through `Closes #N`), then `git -C <repo> worktree remove <worktree>` and `git -C <repo> pull -q`. Post one line: "#N merged: <one-sentence summary> (<PR link>)".
4. **If not:** send concrete feedback to the same Claude Code session, again in the background with `notify_on_complete`:
   `cd <worktree> && claude -r <session_id> -p "<what is wrong and what to change>" --dangerously-skip-permissions --max-turns 100 --output-format json > ~/.local/state/claude-runs/<repo>-issue-N-r<k>.json 2>&1`
   Codex: `cd <worktree> && codex exec resume <session_id> --dangerously-bypass-approvals-and-sandbox --json -o ~/.local/state/claude-runs/<repo>-issue-N-r<k>.summary.txt "<what is wrong and what to change>" > ~/.local/state/claude-runs/<repo>-issue-N-r<k>.jsonl 2>&1`
   Allow at most 2 rework rounds. After that, label it `blocked`, comment on the issue with what is still wrong, tell the user, and move on to the next ticket.

Merging follows your SOUL. **If your SOUL defines a review pipeline** (for example qa and the user's sign-off before any merge), stop at step 2 instead: hand the PR on as your SOUL says, and merge only when it allows. Anything that would deploy, publish or reach outside the repo still needs the user's OK.

## 4. Next ticket

Continue with the next `ready` ticket until none is left, then post a short summary: tickets merged, blocked, and still open.

## Scheduled runs (cron)

A scheduled run ends after its turn, and its background processes end with it, so no completion notice would ever come. In a scheduled run:

- Start Claude Code **detached** so it outlives the run: `setsid -f bash -c 'cd <worktree> && claude -p "$(cat <prompt-file>)" --dangerously-skip-permissions --model <model> --effort <level> --max-turns 200 --output-format json > ~/.local/state/claude-runs/<repo>-issue-N.json 2>&1'`. Codex runs the same way with its step-4 command. Don't wait for it.
- At the start of each scheduled run, review what earlier runs started. A non-empty result JSON (or Codex's summary file) plus a PR means it's ready for step 3. An empty JSON with `pgrep -f "claude -p|codex exec"` still showing it means it's still working: leave it and don't start another.

## When things go wrong

- **CI read fails with HTTP 403 "Resource not accessible by personal access token"** (`gh pr checks`, `statusCheckRollup`): a fine-grained token can't be given the Checks permission. Read the PR head's CI from Actions instead: `gh run list --commit <head-sha>` or `gh api "repos/OWNER/REPO/actions/runs?head_sha=<sha>"`.
- **QA card gating (Kanban):** never create the QA card with your own still-running build card in `parents`: it sits in todo until your card completes, and workers cannot unlink. Create the QA card with no parents, then `kanban_link(parent_id=<qa card>, child_id=<your card>)` so your card waits on QA.
- **Claude Code reports a usage limit or a login error** (`is_error: true`): hand the same ticket to Codex CLI (step 4) in the same worktree, telling it to continue from what is already there, and say so. Use Claude Code again for the next ticket after its reset. If Codex is also limited or not logged in (`codex login status`), stop the queue: put the ticket back to `ready`, tell the user when the limits reset, and resume after that. Never write the code yourself instead.
- **No completion notice arrives** (for example, the gateway restarted and the run was lost): on your next turn, check for `in-progress` issues. If one has a PR, review it. If not, remove its worktree and branch and start that ticket again.
- **Claude Code wants a decision only the user can make:** label `blocked`, ask the user in chat, and continue with other tickets that don't depend on it.
