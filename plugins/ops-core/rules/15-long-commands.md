---
profiles: *
exclude: random
---
- Every tool call is cut off after 7 minutes. Start anything that can run longer than about 5 minutes (full test suites, builds, database resets, image pulls, long scripts) with `terminal` and `background=true`, `notify_on_complete=true`, then carry on or end your turn; when you check on it with `process_manage`, wait at most 5 minutes per call.
