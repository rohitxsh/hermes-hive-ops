#!/bin/bash
# Daily self-check (Hermes cron "self-check", no model). Silent when healthy; otherwise one line per problem, which
# the job posts to ADMIN_DELIVER. Covers what this kit adds on top of vanilla Hermes.
H="$HOME/.hermes"; p=()
HPY=$(ls -d "$H"/tools/python-*/bin/python3 2>/dev/null | sort -V | tail -1)
KIT_PATCHES="$HOME/agents/src/hermes-local-patches"

# gateway service (when it runs under systemd)
if systemctl list-unit-files 'agent-worker@.service' >/dev/null 2>&1 && systemctl cat agent-worker@hermes >/dev/null 2>&1; then
  [ "$(systemctl is-active agent-worker@hermes)" = active ] || p+=("gateway service agent-worker@hermes is not active")
  # every other enabled agent-worker@ service (dashboard, camofox, vaultwarden, ...) must be running too
  for u in $(ls /etc/systemd/system/multi-user.target.wants/ 2>/dev/null | sed -n 's/^agent-worker@\(.*\)\.service$/\1/p'); do
    [ "$u" = hermes ] || systemctl is-active -q "agent-worker@$u" || p+=("agent-worker@$u is $(systemctl is-active "agent-worker@$u") (enabled service not running)")
  done
fi
# coding CLIs still logged in (the fallback coding CLI fails silently otherwise)
[ -x "$HOME/.local/bin/codex" ] && { "$HOME/.local/bin/codex" login status 2>&1 | grep -q "Logged in" || p+=("Codex CLI is not logged in: run codex login --device-auth"); }
# local Hermes patches (a hermes update can drop them)
for f in "$KIT_PATCHES"/*-apply.py; do
  [ -f "$f" ] && grep -q '"--check"' "$f" || continue   # only patches with a report-only mode; others would re-apply
  (cd /tmp && "$HPY" "$f" --check >/dev/null 2>&1) || p+=("Hermes patch $(basename "$f") is missing (hermes update?): re-run setup/install.sh --steps patches, then restart the gateway when idle")
done
# outbound-guard enabled in every profile
for d in "$H" "$H"/profiles/*; do
  [ -f "$d/config.yaml" ] || continue
  { [ -f "$d/plugins/outbound-guard/__init__.py" ] && grep -q "outbound-guard" "$d/config.yaml"; } || p+=("outbound-guard missing or not enabled in $d")
  { [ -f "$d/plugins/ops-core/__init__.py" ] && grep -q "ops-core" "$d/config.yaml"; } || p+=("ops-core missing or not enabled in $d")
  # Hermes keeps only the head and tail of a context file over its limit (6% of the model's window unless
  # context_file_max_chars is set): a SOUL that outgrows it silently loses the middle of its rules.
  lim=$(awk -F': *' '/^context_file_max_chars:/ {print $2+0}' "$d/config.yaml"); sz=$(wc -c < "$d/SOUL.md" 2>/dev/null || echo 0)
  [ "$sz" -le "${lim:-65280}" ] || p+=("SOUL.md in $d is $sz chars, over its ${lim:-65280}-char limit: runs on smaller-window models drop the middle of the rules (set context_file_max_chars in its config.yaml, or trim)")
done
# a local Supabase test stack left running holds about 1 GB and blocks the next run (local-supabase: one per VM)
c=$(docker ps --filter name=supabase_db_ --format "{{.CreatedAt}}" 2>/dev/null | head -1 | cut -d" " -f1,2)
[ -z "$c" ] || [ $(( ($(date +%s) - $(date -d "$c" +%s)) / 3600 )) -lt 3 ] || p+=("a local Supabase stack has been running for over 3 h (forgotten?): local-supabase stop <its repo dir>")
# shared SOUL rules (ops-core): a SOUL rebuilt or edited by hand drops or changes the managed block
out=$("$HOME/.local/bin/hermes" ops-rules check 2>/dev/null | tail -1)
case "$out" in "would update 0 SOUL(s)"|"") ;; *) p+=("shared SOUL rules out of date ($out): run hermes ops-rules apply");; esac
# scheduled jobs failing in any profile
while IFS= read -r line; do [ -n "$line" ] && p+=("$line"); done < <(/usr/bin/python3 - <<'PY'   # system python: PyYAML-free, and a bare python3 under cron can be Hermes's own
import glob, json, os
H = os.path.expanduser("~/.hermes")
for jf in [f"{H}/cron/jobs.json"] + glob.glob(f"{H}/profiles/*/cron/jobs.json"):
    prof = "default" if jf.startswith(f"{H}/cron") else jf.split("/")[-3]
    d = json.load(open(jf)); d = d["jobs"] if isinstance(d, dict) else d
    for j in d:
        if j.get("name") == "self-check":   # its own failure reaches the issue digest as a failed job; listing it here repeats it every day
            continue
        if j.get("enabled", True) and j.get("state") != "paused" and (j.get("failure_streak") or 0) > 0:
            print(f"{prof}: scheduled job '{j['name']}' ({j['id']}) failing: {j.get('last_status')}, {j['failure_streak']} in a row")
        elif j.get("enabled", True) and j.get("state") != "paused" and j.get("last_status") in ("delivery_failed", "blocked_config"):
            # the run worked (or never started) but nobody got its output; Hermes leaves failure_streak at 0 for these
            print(f"{prof}: scheduled job '{j['name']}' ({j['id']}) last run {j['last_status']}: "
                  f"{str(j.get('last_delivery_error') or j.get('last_error') or '')[:200]}")
PY
)
# disk space
use=$(df --output=pcent "$HOME" | tail -1 | tr -dc 0-9); [ "${use:-0}" -ge 85 ] && p+=("home filesystem is ${use}% full")
# second brain
[ -d "$HOME/brain" ] && { git -C "$HOME/brain" rev-parse >/dev/null 2>&1 || p+=("~/brain exists but is not a git repository"); }
# document libraries for the docx/xlsx/powerpoint/pdf skills
/usr/bin/python3 "$HOME/agents/src/doclibs-check/doclibs-check" 2>/dev/null || [ ! -f "$HOME/agents/src/doclibs-check/doclibs-check" ] || p+=("document libraries missing from Hermes's venv: re-run setup/install.sh --steps third-party")
# hermes-talk: a plugin update brings a profile copy's pyproject.toml back, and the next venv sync then fails
for f in "$HOME"/.hermes/profiles/*/plugins/hermes-talk/pyproject.toml; do
  [ -e "$f" ] && p+=("hermes-talk in profile $(basename "$(dirname "$(dirname "$(dirname "$f")")")") has its pyproject.toml back (plugin update?): it collides with the default profile's package and the next venv sync fails; move it to ~/agents/src/talk-pyproject-aside/<profile>/")
done

if [ ${#p[@]} -gt 0 ]; then
  echo "$(hostname) self-check found ${#p[@]} problem(s):"; printf -- '- %s\n' "${p[@]}"; exit 1
fi
