---
profiles: @team *-dev *-qa *-devops
---
- A GitHub Actions run that has sat in "queued" for more than 30 minutes without any job starting, while newer runs do start, is stuck, not busy. Cancel it and re-run it once (`gh run cancel <id>`, then `gh run rerun <id>` or push the same head again), and note it on your card. If it sticks again, file one report-issue. Don't wait hours on a stuck run.
