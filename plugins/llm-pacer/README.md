# llm-pacer

Keeps a minimum gap between a profile's model API calls, so bursts (parallel turns, long tool loops,
cron jobs starting together) don't trip provider rate limits.

Before each model request the plugin books the next free time slot. If the previous request started less
than the gap ago, the request waits in its own turn's thread; other work in the process is not blocked.
A single wait is capped at 30 seconds.

## Use

```bash
hermes plugins install llm-pacer
hermes plugins enable llm-pacer
```

## Config

| Environment variable | Default | Meaning |
|---|---|---|
| `HERMES_LLM_MIN_GAP_SECONDS` | `2` | Minimum seconds between the starts of two model requests in one process. `0` turns pacing off. |

The value is read once when the plugin loads; restart the gateway after changing it.

## What it touches

- **Hooks:** `pre_api_request` only. It never changes the request.
- **Effect to know about:** adds latency. With the default gap, a burst of 5 requests takes at least 8
  seconds to start; pick a smaller gap if your provider allows it.
- **No network calls, no file writes, no shell commands, no credentials.** Waits are logged at INFO level.

## License

MIT
