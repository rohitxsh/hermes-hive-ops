# token-usage

Send `tokens` (or `/tokens`) in any chat and Hermes answers with the model tokens used on this machine:
lifetime and the last 30 days, split into new input, cached input and output, plus the last 30 days by
provider and by profile. The answer comes from Hermes's own session records, so it needs no model call
and still works when every provider is out of quota.

It counts every model call Hermes recorded: chats, cron jobs, compression, approval checks.

## Use

```bash
hermes plugins install token-usage
hermes plugins enable token-usage
```

Then send `tokens` (case and a trailing `?`/`!`/`.` are ignored) or `/tokens` in any gateway chat, or run
`/tokens` in the CLI.

## Config

None.

## What it touches

- **Hooks/commands:** registers the `/tokens` command and a `pre_gateway_dispatch` hook that rewrites a
  message that is exactly `tokens` into `/tokens`. Every other message passes through untouched.
- **Reads outside its own data:** opens `~/.hermes/state.db` and every `~/.hermes/profiles/*/state.db`
  read-only (the `session_model_usage` table). It never writes to them.
- **What the reply shows:** the machine's hostname, token totals, provider names and the names of the five
  busiest profiles. Anyone who can message the gateway can ask, so the reply reaches whoever is in that chat.
- **No network calls, no shell commands, no background work, no credentials.**

## Self-test

```bash
python3 -c "import importlib.util as u,sys; s=u.spec_from_file_location('t','__init__.py'); m=u.module_from_spec(s); s.loader.exec_module(m); m.selftest()"
```

## License

MIT
