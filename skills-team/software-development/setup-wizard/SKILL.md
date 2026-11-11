---
name: setup-wizard
description: >-
  Write an interactive bash script that walks a person, step by step, through a setup only they can do: creating
  accounts or keys in a dashboard, store enrolment, provider credentials, GitHub secrets, a one-off cutover. It opens
  each page, says exactly what to click and copy, takes secrets with hidden input and writes them straight to GitHub
  secrets or a local .env, so nobody pastes a secret into chat. Use when a card waits on a person for credentials or
  dashboard steps (founders' and infra owners' to-dos). Not for steps you can do yourself.
license: MIT (adapted from mattpocock/skills `wizard`, see LICENSE)
---

# Setup wizard

A wizard turns "please do these 14 steps in three dashboards" into one script the person runs at their own pace.
Agents never see the secrets: the person types them into the script on their own machine, and it sends them to where
they belong. [template.sh](template.sh) already has the UX: stage progress, a clean screen per step, opening URLs
(macOS, Linux, WSL, Git Bash), hidden secret entry, idempotent `.env` upserts, `gh secret`/`gh variable` writes
(repo- or environment-scoped via `GH_REPO` / `GH_ENV`) and a closing summary. Your job is the procedure.

## 1. Scope it from the repo first

Read before asking: `.env.example`, README and runbooks, and every `secrets.*` / `vars.*` in `.github/workflows/*`
(each one is a value the wizard may need to produce, and its environment if the workflow uses one). List the stages in
order and, for each captured value: where the person finds it, where it goes (GitHub secret, variable, `.env`, or
nowhere: some stages are pure actions such as "accept the invite"), and whether it is secret.

## 2. Map each stage precisely

Write the path a stranger could follow: URL, then "Dashboard → Settings → API keys → Create key → copy". Where you
don't know the current UI, say so on the card and ask the person who owns that account, rather than guessing.
Note any cost, legal terms or irreversible step: those need the owner's explicit yes and a `confirm` gate.

## 3. Write the script

Copy `template.sh` to the repo (for example `scripts/setup/<topic>.sh`). Replace the example stage with one `stage`
per step, set `TOTAL_STAGES`, and use the helpers: `stage`, `say`/`step`/`note`/`warn`, `open_url`, `ask`/
`ask_secret`, `write_env`, `set_secret`/`set_var`, `pause`, `confirm`. Rules:

- Open the URL before asking for its value; `ask_secret` for anything secret.
- `set_secret` only what CI actually reads, with the exact name from the workflow; set `GH_REPO`/`GH_ENV` at the top
  of `run_wizard` when the workflow uses an environment (for example `GH_ENV=beta`).
- `write_env` only for values a person's local run needs; never write production secrets to a local file.
- `confirm` before anything costly or irreversible.
- No secret, token or personal value is ever hard-coded in the script.

## 4. Check and hand off

- `bash -n` it, and `shellcheck` if available. Don't run it yourself: it opens browsers and waits for a person.
- Trace it statically: every value from step 1 is captured and lands where step 1 said; every secret name matches the
  workflow.
- Put it in a PR (or a draft PR for a one-off) and send the person the link with one line on how to run it
  (`bash scripts/setup/<topic>.sh` on macOS/Linux, or in WSL or Git Bash on Windows; it needs `gh` signed in for the
  GitHub steps). Park the card waiting on them; when they report it done, verify the result (the secret exists in
  the environment, the workflow run passes) before moving on.
- One-off wizards are deleted once used; repeatable setups stay and are linked from the runbook.
