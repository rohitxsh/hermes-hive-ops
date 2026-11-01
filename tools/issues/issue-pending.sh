#!/bin/sh
# Monitor for the "issue handler" job (the owner, 2026-10-26): open alerts the assistant hasn't handled since
# they (re)opened, plus a once-a-day warning review. Stable text: the agent only wakes when this output changes.
/usr/bin/python3 ~/agents/src/issues/issue-digest.py pending
d=$(cat ~/agents/issues/last-warning-review 2>/dev/null)
[ "$d" = "$(date +%F)" ] || echo "WARNING REVIEW DUE (last review: ${d:-never})"
