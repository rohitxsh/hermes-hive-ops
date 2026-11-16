---
profiles: *
exclude: random
---
- Every tool call is cut off after 7 minutes. Start anything that can run longer than about 5 minutes (full test suites, builds, database resets, image pulls, long scripts) with `terminal` and `background=true`, `notify_on_complete=true`, then carry on or end your turn; when you check on it with `process_manage`, wait at most 5 minutes per call.
- Keep each terminal command short. The approval guard refuses a command it cannot parse in full ("command parser limit exceeded"), which happens with long inline GraphQL queries, many chained pipes or large quoted text. Write such a query, script or text to a file in your workspace and run that file (`gh api graphql -F query=@q.graphql`, `python3 script.py`) instead of retrying a shorter variant inline.
