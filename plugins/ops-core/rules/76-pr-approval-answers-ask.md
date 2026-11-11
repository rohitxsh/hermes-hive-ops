---
profiles: *
exclude: random
---
- A PR approval answers the matching chat ask: when you asked a person in chat to approve something and the same thing is up for review in a PR, an approval of that PR by someone allowed to approve it counts as their yes in chat. That means an approving review, or whatever your setup already accepts for PRs that can't get a formal review (a merge, an `approved` label, or an "approved" comment from the owner). Check that both are about the same change and the PR covers everything you asked about; then record it on the card with the review link and carry on, without asking again in chat. The approval covers only what the PR contains: anything your chat ask included beyond it (another decision, money, credentials, production, deleting data) still needs its own answer, so say which part is still open. Commits pushed after the approval follow your existing re-approval rules.
