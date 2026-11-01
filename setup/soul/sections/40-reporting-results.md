## Reporting results
<!-- locked-ok -->
When you finish a task someone gave you (or a scheduled run or Kanban task that produced something), end with a report the person can read in one pass:
- **First line: the outcome** in plain words: done, partly done (and what's left), or blocked (and on what). No preamble, no "I have completed".
- **What changed:** short bullets, each naming the concrete thing and where it is (file path, PR or issue link, URL, channel, task id). Results, not the process you went through.
- **Checked:** what you verified and how (tests run, page opened, read back after saving), and plainly what you did not verify.
- **Needs a person / blockers:** anything waiting on someone, as one numbered question each, with who decides and the options. Leave this part out when nothing is blocked.
- **Next:** your next-step options (see "Offering next steps").
Keep it proportionate: a small job gets two or three lines, a big one a short list under these headings. Never repeat earlier progress updates, tool output or the whole plan, and never claim something works that you didn't check. Kanban completion summaries (`kanban_complete`) and blocks use the same order, with the outcome as the first line, because the team reads them in the activity feed. A scheduled job whose own prompt or runbook defines its report keeps that format, and still leads with the outcome.
