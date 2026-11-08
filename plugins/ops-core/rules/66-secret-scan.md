---
profiles: *-devops
---
- Before you push a branch or open or update a PR, scan the new commits for secrets: `gitleaks git --no-banner --redact --log-opts="origin/<default branch>..HEAD"` in the repo (for files outside git: `gitleaks dir --no-banner --redact <path>`). Exit code 0 means clean. On a finding, don't push: remove the secret from the change (rewrite only your own unpushed commits), and if it was ever pushed or shared, say which credential must be rotated. Report it with `report-issue` naming the file and rule, never the value (`--redact` keeps it out of the output). A finding you verified is a false positive (test fixture, example key) goes in the repo's `.gitleaksignore` with a one-line reason in the PR.
