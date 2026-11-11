---
profiles: @team *-dev *-qa *-devops
---
- In a PR, write "Closes #N" only when merging that PR alone delivers everything the issue tracks. When the issue tracks something that is live only after a deploy, a build, a QA round or later PRs, write "Refs #N", and close the issue when the outcome is actually live or accepted. A merged PR that closes an issue whose work is still going on hides that work from the board.
