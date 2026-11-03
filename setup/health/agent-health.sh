#!/bin/bash
# Daily self-check (Hermes cron "self-check", no model). Silent when healthy; otherwise one line per problem, which
# the job posts to ADMIN_DELIVER. Covers what this kit adds on top of vanilla Hermes.
H="$HOME/.hermes"; p=()
HPY=$(ls -d "$H"/tools/python-*/bin/python3 2>/dev/null | sort -V | tail -1)
KIT_PATCHES="$HOME/agents/src/hermes-local-patches"

# gateway service (when it runs under systemd)
if systemctl list-unit-files 'agent-worker@.service' >/dev/null 2>&1 && systemctl cat agent-worker@hermes >/dev/null 2>&1; then
  [ "$(systemctl is-active agent-worker@hermes)" = active ] || p+=("gateway service agent-worker@hermes is not active")
fi
# local Hermes patches (a hermes update can drop them)
for f in "$KIT_PATCHES"/*-apply.py; do
  [ -f "$f" ] && grep -q '"--check"' "$f" || continue   # only patches with a report-only mode; others would re-apply
  (cd /tmp && "$HPY" "$f" --check >/dev/null 2>&1) || p+=("Hermes patch $(basename "$f") is missing (hermes update?): re-run setup/install.sh --steps patches, then restart the gateway when idle")
done
# outbound-guard enabled in every profile
for d in "$H" "$H"/profiles/*; do
  [ -f "$d/config.yaml" ] || continue
  { [ -f "$d/plugins/outbound-guard/__init__.py" ] && grep -q "outbound-guard" "$d/config.yaml"; } || p+=("outbound-guard missing or not enabled in $d")
done
# scheduled jobs failing in any profile
while IFS= read -r line; do [ -n "$line" ] && p+=("$line"); done < <(python3 - <<'PY'
import glob, json, os
H = os.path.expanduser("~/.hermes")
for jf in [f"{H}/cron/jobs.json"] + glob.glob(f"{H}/profiles/*/cron/jobs.json"):
    prof = "default" if jf.startswith(f"{H}/cron") else jf.split("/")[-3]
    d = json.load(open(jf)); d = d["jobs"] if isinstance(d, dict) else d
    for j in d:
        if j.get("enabled", True) and j.get("state") != "paused" and (j.get("failure_streak") or 0) > 0:
            print(f"{prof}: scheduled job '{j['name']}' ({j['id']}) failing: {j.get('last_status')}, {j['failure_streak']} in a row")
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
