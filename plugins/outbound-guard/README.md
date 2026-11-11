# outbound-guard

Asks for approval before a tool call sends what looks like a payment card number, an Indian Aadhaar
number or an Indian PAN off the machine. It is a `pre_tool_call` hook that escalates the call to Hermes's
normal approval prompt; under cron and other unattended runs, where nobody can approve, the call is blocked.

## What it checks

- **Always checked:** `send_message`, `discord*` tools, `browser_type`, `browser_navigate`,
  `browser_console`, `browser_exec`, `browser_cdp`, `web_search`, `web_extract`, `x_search`,
  `delegate_task` (all arguments).
- **Checked when they look like network use:** `terminal` commands that mention curl, wget, ssh, scp,
  rsync, nc, mail tools, `gh`, `git push` and similar; `execute_code` code that mentions requests, urllib,
  httpx, aiohttp, smtplib, socket, fetch and similar.
- **Patterns:** card numbers that pass the Luhn check and have a known issuer prefix; 12-digit Aadhaar
  numbers that pass the Verhoeff check; PANs (`AAAPA9999A` shape). Hex IDs, long numeric IDs and
  `YYYYMMDD-HHMM` stamps are ignored.
- **Uploaded files:** local files those calls send are read and checked too: curl `@file`, `-T`/`--upload-file`,
  `-d`/`--data-binary`/`-F` file arguments, `gh --body-file`/`-F`, `scp`/`rsync` sources, `MEDIA:/path`
  attachments and file paths given as message arguments. A file that exists but can't be read, or a text file
  over 20 MB, needs approval as well. Relative paths resolve against the call's `workdir` (or the terminal's
  start folder); one that doesn't resolve is skipped.
- **Not checked:** bank account numbers (no reliable pattern), anything local (`read_file`, a terminal
  command with no network tool), `browser_vault` fills (the agent never sees those values), binary uploads
  (images, APKs) and files that `execute_code` opens itself. Treat the guard as text detection, not a full
  data-loss filter.

Approving with "always" covers only that exact call (the rule key is a hash of the checked text).

## Use

```bash
hermes plugins install outbound-guard
hermes plugins enable outbound-guard
```

## Config

None.

## What it touches

- **Hooks:** `pre_tool_call` only. It returns an approval request when it finds a match, and nothing
  otherwise; a bug in the detection never blocks a tool call. Logging is separate: if the log can't be
  written (full disk, permissions), the approval is still required.
- **Writes:** one line per match to `~/.hermes/logs/outbound-guard.log` with time, profile, tool name and
  the masked value (`****1111`). Full values are never written.
- **No network calls, no shell commands, no background work, no credentials.**
- **Limits:** pattern matching, not a data-loss-prevention system. Values that are split, encoded or
  reformatted get through, and a false positive costs one approval prompt.

## Self-test

```bash
python3 __init__.py
```

## License

MIT
