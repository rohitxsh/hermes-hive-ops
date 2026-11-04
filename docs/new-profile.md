# Creating, renaming and checking a Hermes profile on this VM

How profiles are set up here, from what the setups on 2026-10-26 actually needed. Follow it whenever the owner asks for a new profile (or a renamed one), then run the checks at the end. Back up every file before you change it, and log the change in ~/agents/ADMIN-CHANGES.md.

## 1. Agree the basics
- **Name:** lowercase, words joined by hyphens (for example `project-dev`). It becomes the folder, the route target and the Kanban assignee.
- **Purpose:** one or two sentences, used for `--description` and the SOUL role.
- **Where the owner talks to it:** a Discord channel ID, or a thread ID plus its parent channel. The owner creates the channel; ask for the ID.
- **Source profile to clone:**
  - tools for general working profiles;
  - a project-* profile for a new Project team role;
  - never default (the admin, with sudo) or a locked profile (locked down, no tools).

## 2. Create it
```bash
hermes profile create <name> --clone-from <source> --no-alias --description "<purpose>"
cp -a --update=none ~/.hermes/profiles/<source>/plugins/. ~/.hermes/profiles/<name>/plugins/   # the clone does NOT copy plugins
mkdir -p ~/work/<name>
hermes --profile <name> config set terminal.cwd ~/work/<name>
```
The clone copies config.yaml, .env, SOUL.md and skills. Its config already carries the house settings (fallback chain, `secrets.command`, smart approvals with the owner policy and deny rules, 3 h approval timeout, 15 min Discord buttons, queue mode, compression, searxng-tuned and local-extract, Discord display settings); keep them.

## 3. Fix the .env (each profile gets ONLY its own .env, never the service environment)
- **Discord settings:** the clone drops these; copy them from the source and point them at the new channel:
  - `DISCORD_ALLOWED_USERS` (same as the source);
  - `DISCORD_REQUIRE_MENTION` (same as the source);
  - `DISCORD_FREE_RESPONSE_CHANNELS=<channel id>` (with the overlay's `discord.free_response_auto_thread: true`, each new message there still starts its own thread);
  - `DISCORD_HOME_CHANNEL=<channel id>`.
- **Keys every profile needs:** `SEARXNG_URL`, `BROWSER_PATH`, `HERMES_CRON_TIMEOUT` and `TERMINAL_TIMEOUT`. Without `SEARXNG_URL`, search silently falls back to the cloud; without `BROWSER_PATH`, chart PNG export fails.
- **Credentials:** never put them in .env. They come from sealed credentials through `secrets.command` (`hermes-sealed-env ...`).

## 4. Write the SOUL
- **Replace only the source's `## Role: ...` section** with the new role:
  - what it does;
  - its working folder;
  - what needs the owner's OK (publishing, logins, spending, contacting people);
  - "ask the main assistant with the `consult-assistant` skill" for context about the owner.
- **Keep the shared sections:** Claude execution policy, Model quota, Auto mode, Character, When something fails, Visual Deliverables.
- **Remove what only fit the source**, for example the source's GitHub/PR rules.
- **Moving an existing conversation into the new profile:** export its session from the old profile's state.db (user and assistant messages, no tool calls, skip compaction markers) into `HANDOFF-....md` in the working folder, and tell the SOUL to read it first.

## 5. Route the channel to it (main config, ~/.hermes/config.yaml)
- Add an entry to `gateway.profile_routes`, keeping every existing entry. Read the guild_id from an existing route:
  - `{name: <name>-channel, platform: discord, guild_id: <guild>, chat_id: <channel id>, profile: <name>}`;
  - for a thread, also give `thread_id`, with `chat_id` set to the parent channel. A thread route beats its channel's route.
- Write the whole list back with `hermes config set gateway.profile_routes '<JSON list>'`.
- `kanban.dispatch_profiles` gets new profiles automatically (the quota governor maintains it). Check that the name is there.

## 6. Load and verify
```bash
sudo systemd-run --unit hermes-restart-idle --collect ~/.local/bin/hermes-restart-idle --webui
grep -a "Cron scheduler will tick" ~/.hermes/logs/gateway.log | tail -1   # the new name must be in the list
bash ~/.hermes/scripts/agent-health.sh                                       # must print nothing (clean)
```
- The issue digest, quota governor, approval pings and token report pick the profile up on their own.
- Then ask the owner to send a test message in the channel. Check the gateway log shows it routed to the new profile.

## Renaming a profile
- **Rename it:** `hermes profile rename <old> <new>` moves the folder and migrates sessions and routing identity. It does **not** touch:
  - `gateway.profile_routes` (profile and route names) and `kanban.dispatch_profiles` in the main config;
  - `terminal.cwd` and the work folder: move it, then set the cwd again;
  - mentions in other profiles' SOULs and in ~/agents/src sources: search for the old name (and role words);
  - open Kanban tasks: `hermes kanban reassign <task> <new>`;
  - Discord thread names: renamed through the Discord bot API with the sealed bot token. The owner renames channels themselves.
- **Then** restart with hermes-restart-idle and run the same checks.

## Never
- Clone default or a locked profile.
- Copy another profile's cron jobs or memories into a new profile.
- Put tokens in .env or config.
- Restart with a plain `systemctl restart`. hermes-restart-idle waits until nothing is running.
- Delete a profile without the owner's explicit OK. Back up its folder first.
