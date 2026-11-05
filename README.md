# hermes-ops-kit

**Rohit's opinionated setup for [Hermes Agent](https://github.com/NousResearch/hermes-agent).** It turns a vanilla
Hermes install into an always-on team of agents on a small Linux VM: several profiles behind one gateway (Discord),
Kanban that repairs its own stuck cards, shared agent rules kept in one place (the `ops-core` plugin), scheduled
maintenance, safer approvals, memory that learns, and fixes for problems hit in daily use.
It is one way of running Hermes, not the only one. Everything here ran in production on Hermes **v0.22.6**.

## Quick start (from a vanilla Hermes install)

```bash
git clone https://github.com/rohitxsh/hermes-ops-kit && cd hermes-ops-kit
cp setup/settings.env.example setup/settings.env      # fill it in (nothing secret)
setup/install.sh --dry-run                            # see what it would do
setup/install.sh                                      # bin tools plugins patches skills third-party config soul health jobs brain
sudo setup/services/install-services.sh "$USER" hermes   # optional: run the gateway as a systemd service
setup/devtools/install-devtools.sh claude codex gh rtk context7   # optional: coding CLIs (+ RTK, Context7) for coding agents
hermes-restart-idle                                   # restart the gateway when no turn is running
```

Every step is idempotent and keeps a backup of what it changes (`*.bak-kit`). Run a single step with
`--steps patches,config`. After every `hermes update`, run `setup/install.sh --steps patches` (the daily self-check
tells you when an update dropped a patch). Since v0.22.6 the built-in browser tools are gone from core: Camofox is the
catalog plugin `camofox` (Hermes installs it for homes that use Camofox), and a home that had `browser.backend: off`
needs `agent.disabled_toolsets: [browser]` to stay browser-free. An update or a plugin install can re-sync Hermes's venv
and drop the document libraries; `setup/install.sh --steps third-party` puts them back (the self-check reports it).
Before changing the kit, run `setup/test-vanilla.sh`: it installs the kit twice into a throwaway home holding
vanilla Hermes and checks patches, tools, jobs and the self-check, without touching your real `~/.hermes`.

## Manual steps the installer can't do for you

- **Secrets.** Nothing secret lives in files. Seal each one with systemd-creds, typing the value yourself:
  `read -rsp 'value: ' T && printf %s "$T" | sudo systemd-creds encrypt --name=<name> - /etc/credstore.encrypted/<name>; unset T`.
  Services read them through `LoadCredentialEncrypted=` drop-ins; profiles through `bin/hermes-sealed-env`
  (map in `~/.config/hermes-sealed-env.conf`); git and gh through `bin/git-credential-sealed`
  (map in `~/.config/git-credential-sealed.map`). Examples in `setup/examples/`.
- **Profiles and chat routing.** Create your profiles with `hermes profile create`, give each its Discord channel in
  its `.env`, and list web-only chat profiles in `LOCKED_PROFILES` before running the config step. See
  `docs/new-profile.md`.
- **Sign-ins.** Model providers, Claude Code, Codex and gh are signed in by you.
- **Voice.** Discord voice playback needs the Opus codec, a system package: `sudo apt-get install libopus0`. For Talk in
  Discord voice, list who may run mutating tools by voice in each profile's `.env`: `TALK_DISCORD_OPERATOR_USER_IDS=<ids>`.
- **Optional services:** SearXNG (set `SEARXNG_URL` per profile), Camofox, Vaultwarden, the web UIs; see
  `setup/services/` and `setup/third-party/install.sh`.

## What's inside

### `setup/` — the installer and the setup layer
| Part | What it does |
|---|---|
| `install.sh`, `settings.env.example` | Orchestrates every step below from your settings |
| `config/overlay.yaml`, `locked.yaml` | The settings this kit runs with (smart approvals with a written policy and deny list, compression at 200k tokens, queued input, tool lines kept out of chat, loop-guard limits, holographic memory, SearXNG search, local extraction, Camofox browser, sealed secrets). `locked.yaml` makes a profile a web-only chat. Applied with comments preserved. |
| `soul/sections/` | Generic SOUL sections appended to every profile: character, usage limits, auto mode, failures, visuals, avoiding loops, status questions, reporting results, next steps, memory, long messages, second brain, attention. Plus the i-have-adhd reply format when that skill is installed. |
| `jobs/` | Generic maintenance jobs: self-check, quota guard, approval notify, gateway heal, backup, issue digest and handler, memory learn and export, update notice, attention check, PR resume, skill review, Kanban feed, board sync, kanban doctor (repairs stuck Kanban cards that aren't waiting on a person) |
| `services/` | One systemd template (`agent-worker@<name>`) and run scripts for the gateway, WebUI, dashboard, Workspace, Camofox and Vaultwarden; secrets only via sealed credentials |
| `health/agent-health.sh` | Daily self-check: silent when healthy, one line per problem |
| `brain/setup-brain.py` | `~/brain`, plain-Markdown long-term notes in local git, filed nightly by memory-learn |
| `third-party/install.sh` | Pinned third-party pieces (below) |
| `devtools/` | Claude Code, Codex CLI, gh, Flutter, Supabase CLI with checksum checks; RTK 1.1.0 (condensed Bash output, hooked into Claude Code) and the Context7 MCP for Claude Code |

### `patches/` — fixes to Hermes itself
Each `*-apply.py` is idempotent, keeps a `.bak`, and (where marked) supports `--check` and `--test`.

| Patch | What it fixes | Upstream (NousResearch/hermes-agent) |
|---|---|---|
| `kanban-guardrail-block-apply.py` | A loop-guard halt in a Kanban worker blocks the card with the reason instead of a protocol-violation crash and restart | PR #103907 (open) |
| `pr-rules-plan-apply.py` | GitHub's 403 "Upgrade to GitHub Pro" on the rulesets endpoint no longer breaks the Kanban PR gate | PR #143935 (open) |
| `leading-mention-apply.py` | A Discord message that starts with an @mention of someone else is ignored by every agent (keep it: the `ops-core` plugin's `pre_gateway_dispatch` hook is only a fallback, because Discord's 👀 reaction and typing indicator start before plugin hooks run; with the hook alone the agent stays silent but still shows those) | PR #120266 (open; leading mode suggested) |
| `kanban-list-fence-apply.py` | `hermes kanban list` works inside a delegated helper (it skips only the ready-lane refresh the fence refuses) | issue #148926 |
| `kanban-stale-auth-apply.py` | A quota error left by an older run no longer holds a card forever after a later run ended normally | issue #138618; fix PRs open, e.g. #141740 |
| `upload-selector-apply.py` | Camofox: reliable file-upload selectors (patches the Camofox server, not Hermes) | Camofox server, not Hermes |
| `failed-turn-reaction-apply.py` | A failed turn gets a reaction instead of silence | issue #112917 |
| `queued-reaction-apply.py` | Messages queued while an agent is busy get the same 👀/✅ reactions as direct ones | PRs #148610, #148611 |
| `loop-hold-apply.py` | A card Hermes sent to triage for looping blocks waits for its owner instead of being re-promoted (or fanned out) by the auto-decomposer; once the owner edits or reassigns it, it is released as written | issue #109453 |
| `backup-vanished-apply.py` | `hermes backup` no longer fails when the scheduler deletes its own short-lived job files mid-backup; any other missing file still fails it | PR #147369 (open) |
| `md-as-pdf-apply.py` | Every Markdown attachment (chat replies, scheduled and Kanban deliveries) goes out as its formatted PDF via `md-pdf`, so people get one readable file; falls back to the `.md` on failure | none (needs the local `md-pdf`) |
| `kanban-wake-only-apply.py` | Kanban subscriptions made from a chat wake the agent instead of posting raw pings with card IDs and re-uploading files named in completion summaries; switch existing ones with `hermes kanban notify-subscribe … --delivery-mode wake` | issue #147262, PR #139034 |
| `kanban-show-compact-apply.py` | `kanban_show` called by an orchestrator (not the dispatched worker reading its own card) leaves out `worker_context` and keeps the last 10 events instead of 50: about half the size on large cards (measured 125k → 63k chars). `--check`, `--test` | PR #145090 (open) |
| `queued-typing-apply.py` | A message queued while the agent is busy shows the Discord typing indicator again as soon as its turn starts (the restart was a no-op while the old 12 s typing loop ran, so the queued turn often showed none) | PR #148598 |
| `kanban-pr-guard-author-apply.py` | The duplicate-PR guard (`active_pr`) counts only PR links in comments by the card's own assignee, so a PM or reviewer citing a PR no longer holds an unrelated ready card for 24 h ("kanban dispatcher stuck") | PR #146075 (open) |
| `smart-unattended-apply.py` (+ `.patch`, test) | Smart approvals also for unattended runs (cron, Kanban) | PRs #98873 (cron), #135169 (verdict parsing) |
| `discord-slash-auth-late-dependency.patch`, `team-notification-here.patch` | Slash-command auth with a late dependency; opt-in team `@here` notifications, and a leading `@silent` sends a post without a push or sound (keep text on the same line, e.g. `@silent **Report**`: cron reads a lone `@silent` line as `[SILENT]` and posts nothing) (`git apply`; made against v0.22.6) | PR #146972; `@silent`: issue #148594 |

Drop a patch once its upstream fix is in the Hermes release you run (each patch's `--check` then reports the anchor missing, and the health check flags it).

### `plugins/`
`outbound-guard` (card/Aadhaar/PAN leaving the machine needs approval), `approval-notify`, `ask-assistant` (a locked
profile can ask the admin profile), `token-usage`, `quota-alert`, `codex-usage-alert`, `llm-pacer`, `searxng-tuned`,
`local-extract`, `vault-guard`, `quota-retry` (a chat message that failed because every provider was out of quota is retried once quota is back, or the agent asks first if tools had already run; needs `plugins.entries.quota-retry.allow_gateway_injection: true`), `ops-core` (the orchestration plugin, enabled in every profile: shared SOUL rules kept in one place (rule files in `plugins/ops-core/rules/` plus your own in `~/agents/rules/`, written into one managed block per SOUL by `hermes ops-rules apply`; `check` reports drift); `hermes ops <tool>` runs the kit's tools (doctor, pending, issues, attention, board-sync, feeds, quota); a newly stuck Kanban card starts the `kanban doctor` job within about five minutes instead of waiting for its half-hourly run; and a message that starts with @someone else is left to that person, as a fallback for the `leading-mention` patch).

### `tools/` and `bin/`
`attention` (`waiting-on-me`, `follow-up`, `renewals`, and `pr-resume`: a blocked Kanban card resumes by itself once its PR is approved or merged, or with a review-feedback note when a reviewer requests changes; list the agents' own GitHub logins in `~/agents/attention/config.json` `agent_github_logins` to also wake on human comments), `memory-learn` (set `HERMES_OWNER_USER_ID`), `memory-export`,
`kanban-feed`, `restart-idle`, `consult`, `my-messages`, `quota` (`quota-status`, `automode`), `issues`,
`gateway-heal`, `speed-tune`, `efficiency` (where quota and time go: per card, job, thread and profile; waste rates; skill reloads), `skill-review` (weekly: an agent proposes one fix to the worst-performing own skill, applied only on your OK), `feeds` (reads a shared Miniflux feed reader with no model calls: `new` since this profile last looked, `search`, `list`, `add`, `filter`, `remove`; each profile keeps its own cursor, nothing is marked read; set `MINIFLUX_URL` and seal the API key as `miniflux_api_key`), `md-pdf` (Markdown to a formatted PDF with Hermes's own Chromium; raw HTML escaped), `discord-send` (lets a Kanban worker or script with no Discord token post a message and files to a known channel or thread: the gateway delivers it through a one-shot job and the command waits for the result; a .md is sent as its formatted PDF), `kanban-doctor` (lists Kanban cards that look stuck, with no model calls; the `kanban doctor` job repairs the ones not waiting on a person, and `release` frees a card held after a block loop), `pending-human` (cards and PRs waiting on a person, for a PM's evening summary or "what's waiting on me?"; map profiles to repos in `~/agents/pending-human/config.json`), `board-sync` (keeps a GitHub Projects board's lanes in step with PR/issue state and labels: drafts and changes-requested go to In Progress, and a PR reaches Awaiting Human Approval only with a QA certificate in `~/agents/board-sync/qa-acceptances.json` (format in `qa-acceptances.example.json`); any bad GitHub data stops the run before it writes, and `--dry-run` never writes; enable it by writing `~/agents/board-sync/config.json` with `owner`, `project` and `repo`, plus optional `lanes` to rename lanes and `qa_acceptances` for another certificate path), `artifacts` (`publish-artifact`), `token-stats`, `maintenance` (backup, update notice,
usage report), `doclibs-check`; commands `hermes-sealed-env`, `git-credential-sealed`, `gh` (per-repo token
wrapper), `report-issue`, `vault-fill`.

### `skills/`
`claude-code-tickets` (coding work through Claude Code, Codex as fallback), `consult-assistant`, `vault-logins`,
`markitdown`, `interactive-visuals`, `feeds` (check feeds before web-searching for releases and news; keep the subscriptions tidy).

Adapted from Google's [elephant-goldfish-model](https://github.com/google/elephant-goldfish-model) (Apache-2.0, license
in each folder): `independent-review` (fresh read-only subagents review a contract or PRD before work starts:
first-read paraphrase, design critique, build readiness; 🔴/🟡/🟢 findings answered with propose fix /
contest / escalate / decline; one re-audit at most), `drift-report` (design docs vs code on the default branch, in a
temporary worktree; schedule it weekly as a monitor-gated job whose script prints `origin/main` and a digest of the
design docs) and `docs-bootstrap` (contract-style READMEs for code that has no design docs).

## Third-party pieces (installed by `setup/third-party/install.sh`, not copied here)

[obra/superpowers](https://github.com/obra/superpowers) @ 2ce8aa15 (its session-start injection is turned off by
`tools/speed-tune`), [holographic](https://github.com/itpartypattaya/hermes-plugin-holographic) @ b81f060,
[claude-subscription-directsdk](https://github.com/NousResearch/hermes-official-plugins) @ 54afaf5,
[cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill) @ c1c8a8c,
[ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) @ 1ecea19,
Anthropic's [data-visualization](https://github.com/anthropics/knowledge-work-plugins) @ 2574e29 and
[frontend-design](https://github.com/anthropics/claude-plugins-official),
camofox-browser 1.18.1, markitdown 0.1.9, Hermes's `edge-tts` and `stt-whisper` extras (local Whisper `small`),
the catalog plugins `hermes-talk` 0.22.1 (realtime voice on the ChatGPT subscription; non-default profile copies keep
their `pyproject.toml` aside, or the shared venv refuses a second `hermes-talk` package) and `memory-wiki`,
[Agent Reach](https://github.com/Panniantong/Agent-Reach) 1.6.1 (release wheel, sha256 pinned, uv-managed Python), [hermes-webui](https://github.com/nesquena/hermes-webui) v0.52.544,
[hermes-workspace](https://github.com/outsourc-e/hermes-workspace) v2.3.0.

### Attention renewals

`~/agents/attention/config.json` lists `domains` (expiry via RDAP) and optional `renewal_commands`: commands that print
a date, each run once a day, for subscriptions with a status command. For example, a data-plan check:
`{"name": "Data plan", "command": "plan-status", "pattern": "validUntil\s+(\S+)", "note": "renew it"}`.
For `pr-resume`: `github_owner` (whose comment approvals count; unset: any human except `agent_github_logins`),
`agent_github_logins` (the agents' own GitHub accounts, ignored), and `owner_gate_labels` (default `["human-signoff"]`):
PR labels that mean a person must approve, so QA's `qa-passed` label alone doesn't wake the waiting card.

## Conventions

Hermes at `~/.hermes`; kit tools in `~/agents/src/`, commands in `~/.local/bin`; secrets in `/etc/credstore.encrypted`;
scheduled scripts run as Hermes cron jobs and stay silent when there is nothing to say. Chat IDs in tests are fake.

## License

MIT, see `LICENSE`. The patch scripts contain short excerpts of Hermes Agent code (MIT, © Nous Research).
