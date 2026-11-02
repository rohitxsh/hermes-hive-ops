# hermes-ops-kit

**Rohit's opinionated setup for [Hermes Agent](https://github.com/NousResearch/hermes-agent).** It turns a vanilla
Hermes install into an always-on team of agents on a small Linux VM: several profiles behind one gateway (Discord),
Kanban, scheduled maintenance, safer approvals, memory that learns, and fixes for problems hit in daily use.
It is one way of running Hermes, not the only one. Everything here ran in production on Hermes **v0.22.5**.

## Quick start (from a vanilla Hermes install)

```bash
git clone https://github.com/rohitxsh/hermes-ops-kit && cd hermes-ops-kit
cp setup/settings.env.example setup/settings.env      # fill it in (nothing secret)
setup/install.sh --dry-run                            # see what it would do
setup/install.sh                                      # bin tools plugins patches skills third-party config soul health jobs brain
sudo setup/services/install-services.sh "$USER" hermes   # optional: run the gateway as a systemd service
setup/devtools/install-devtools.sh claude codex gh    # optional: coding CLIs for coding agents
hermes-restart-idle                                   # restart the gateway when no turn is running
```

Every step is idempotent and keeps a backup of what it changes (`*.bak-kit`). Run a single step with
`--steps patches,config`. After every `hermes update`, run `setup/install.sh --steps patches` (the daily self-check
tells you when an update dropped a patch).
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
- **Optional services:** SearXNG (set `SEARXNG_URL` per profile), Camofox, Vaultwarden, the web UIs; see
  `setup/services/` and `setup/third-party/install.sh`.

## What's inside

### `setup/` — the installer and the setup layer
| Part | What it does |
|---|---|
| `install.sh`, `settings.env.example` | Orchestrates every step below from your settings |
| `config/overlay.yaml`, `locked.yaml` | The settings this kit runs with (smart approvals with a written policy and deny list, compression at 200k tokens, queued input, tool lines kept out of chat, loop-guard limits, holographic memory, SearXNG search, local extraction, Camofox browser, sealed secrets). `locked.yaml` makes a profile a web-only chat. Applied with comments preserved. |
| `soul/sections/` | Generic SOUL sections appended to every profile: character, usage limits, auto mode, failures, visuals, avoiding loops, status questions, reporting results, next steps, memory, long messages, second brain, attention. Plus the i-have-adhd reply format when that skill is installed. |
| `jobs/` | Generic maintenance jobs: self-check, quota guard, approval notify, gateway heal, backup, issue digest and handler, memory learn and export, update notice, attention check, PR resume, skill review, Kanban feed |
| `services/` | One systemd template (`agent-worker@<name>`) and run scripts for the gateway, WebUI, dashboard, Workspace, Camofox and Vaultwarden; secrets only via sealed credentials |
| `health/agent-health.sh` | Daily self-check: silent when healthy, one line per problem |
| `brain/setup-brain.py` | `~/brain`, plain-Markdown long-term notes in local git, filed nightly by memory-learn |
| `third-party/install.sh` | Pinned third-party pieces (below) |
| `devtools/` | Claude Code, Codex CLI, gh, Flutter, Supabase CLI with checksum checks |

### `patches/` — fixes to Hermes itself
Each `*-apply.py` is idempotent, keeps a `.bak`, and (where marked) supports `--check` and `--test`.

| Patch | What it fixes |
|---|---|
| `kanban-guardrail-block-apply.py` | A loop-guard halt in a Kanban worker blocks the card with the reason instead of a protocol-violation crash and restart |
| `pr-rules-plan-apply.py` | GitHub's 403 "Upgrade to GitHub Pro" on the rulesets endpoint no longer breaks the Kanban PR gate |
| `leading-mention-apply.py` | A Discord message that starts with an @mention of someone else is ignored by every agent |
| `camofox-410-apply.py`, `upload-selector-apply.py` | Camofox: recover from dead tabs; reliable file-upload selectors |
| `failed-turn-reaction-apply.py` | A failed turn gets a reaction instead of silence |
| `queued-reaction-apply.py` | Messages queued while an agent is busy get the same 👀/✅ reactions as direct ones |
| `loop-hold-apply.py` | A card Hermes sent to triage for looping blocks waits for its owner instead of being re-promoted (or fanned out) by the auto-decomposer; once the owner edits or reassigns it, it is released as written |
| `backup-vanished-apply.py` | `hermes backup` no longer fails when the scheduler deletes its own short-lived job files mid-backup; any other missing file still fails it |
| `smart-unattended-apply.py` (+ `.patch`, test) | Smart approvals also for unattended runs (cron, Kanban) |
| `cron-shared-bot-delivery.patch`, `discord-slash-auth-late-dependency.patch`, `team-notification-here.patch` | Cron delivery with a shared bot; slash-command auth with a late dependency; opt-in team `@here` notifications |

### `plugins/`
`outbound-guard` (card/Aadhaar/PAN leaving the machine needs approval), `approval-notify`, `ask-assistant` (a locked
profile can ask the admin profile), `token-usage`, `quota-alert`, `codex-usage-alert`, `llm-pacer`, `searxng-tuned`,
`local-extract`, `vault-guard`.

### `tools/` and `bin/`
`attention` (`waiting-on-me`, `follow-up`, `renewals`, and `pr-resume`: a blocked Kanban card resumes by itself once its PR is approved or merged, or with a review-feedback note when a reviewer requests changes; list the agents' own GitHub logins in `~/agents/attention/config.json` `agent_github_logins` to also wake on human comments), `memory-learn` (set `HERMES_OWNER_USER_ID`), `memory-export`,
`kanban-feed`, `restart-idle`, `consult`, `my-messages`, `quota` (`quota-status`, `automode`), `issues`,
`gateway-heal`, `speed-tune`, `efficiency` (where quota and time go: per card, job, thread and profile; waste rates; skill reloads), `skill-review` (weekly: an agent proposes one fix to the worst-performing own skill, applied only on your OK), `discord-send` (lets a Kanban worker or script with no Discord token post a message and files to a known channel or thread: the gateway delivers it through a one-shot job and the command waits for the result), `board-sync` (keeps a GitHub Projects board's lanes in step with PR/issue state and labels; enable it by writing `~/agents/board-sync/config.json` with `owner`, `project` and `repo`), `artifacts` (`publish-artifact`), `token-stats`, `maintenance` (backup, update notice,
usage report), `doclibs-check`; commands `hermes-sealed-env`, `git-credential-sealed`, `gh` (per-repo token
wrapper), `report-issue`, `vault-fill`.

### `skills/`
`claude-code-tickets` (coding work through Claude Code, Codex as fallback), `consult-assistant`, `vault-logins`,
`markitdown`, `interactive-visuals`.

## Third-party pieces (installed by `setup/third-party/install.sh`, not copied here)

[obra/superpowers](https://github.com/obra/superpowers) @ 2ce8aa15 (its session-start injection is turned off by
`tools/speed-tune`), [holographic](https://github.com/itpartypattaya/hermes-plugin-holographic) @ b81f060,
[claude-subscription-directsdk](https://github.com/NousResearch/hermes-official-plugins) @ 54afaf5,
[cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill) @ c1c8a8c,
[ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) @ 1ecea19,
Anthropic's [data-visualization](https://github.com/anthropics/knowledge-work-plugins) @ 2574e29 and
[frontend-design](https://github.com/anthropics/claude-plugins-official),
camofox-browser 1.18.1, markitdown 0.1.9, [hermes-webui](https://github.com/nesquena/hermes-webui) v0.52.544,
[hermes-workspace](https://github.com/outsourc-e/hermes-workspace) v2.3.0.

## Conventions

Hermes at `~/.hermes`; kit tools in `~/agents/src/`, commands in `~/.local/bin`; secrets in `/etc/credstore.encrypted`;
scheduled scripts run as Hermes cron jobs and stay silent when there is nothing to say. Chat IDs in tests are fake.

## License

MIT, see `LICENSE`. The patch scripts contain short excerpts of Hermes Agent code (MIT, © Nous Research).
