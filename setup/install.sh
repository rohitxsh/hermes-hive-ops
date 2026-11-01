#!/bin/bash
# Bring a vanilla Hermes install up to this kit's setup. Every step is idempotent and backs up what it changes.
#   setup/install.sh                  all steps except services and devtools (those need sudo / downloads)
#   setup/install.sh --steps a,b      only these steps
#   setup/install.sh --dry-run        print what each step would do
# Steps, in order: bin tools plugins patches skills third-party config soul health jobs brain [services devtools]
set -euo pipefail
KIT=$(cd "$(dirname "$0")/.." && pwd)
SETUP="$KIT/setup"
[ -f "$SETUP/settings.env" ] || { echo "Copy setup/settings.env.example to setup/settings.env and fill it in first."; exit 1; }
set -a; . "$SETUP/settings.env"; set +a
STEPS="bin tools plugins patches skills third-party config soul health jobs brain"   # health before jobs: the self-check job needs its script
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --steps) STEPS=$(echo "$2" | tr ',' ' '); shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown option $1"; exit 1 ;;
  esac
done
export KIT SETUP DRY
HH="$HOME/.hermes"; BIN="$HOME/.local/bin"; SRC="$HOME/agents/src"
[ -x "$BIN/hermes" ] || { echo "Hermes isn't installed at $BIN/hermes. Install vanilla Hermes first."; exit 1; }
VENV_PY=$(python3 -c "import json,glob,os;f=sorted(glob.glob(os.path.expanduser('~/.hermes/installs/*/facts.json')),key=os.path.getmtime)[-1];print(json.load(open(f))['packages']['venv']['environment']+'/bin/python')")
HPY=$(ls -d "$HH"/tools/python-*/bin/python3 | sort -V | tail -1)
export VENV_PY HPY
run() { if [ "$DRY" = 1 ]; then echo "  would: $*"; else "$@"; fi; }
profiles() { echo default; for d in "$HH"/profiles/*/; do [ -f "$d/config.yaml" ] && basename "$d"; done; }
home_of() { [ "$1" = default ] && echo "$HH" || echo "$HH/profiles/$1"; }
is_locked() { case " $LOCKED_PROFILES " in *" $1 "*) return 0;; esac; return 1; }

step_bin() {   # helper commands into ~/.local/bin
  run mkdir -p "$BIN"
  for f in "$KIT"/bin/*; do run install -m 755 "$f" "$BIN/$(basename "$f")"; done
}
step_tools() {  # tools into ~/agents/src, commands linked into ~/.local/bin, scheduled scripts into ~/.hermes/scripts
  run mkdir -p "$SRC" "$HH/scripts"
  for d in "$KIT"/tools/*/; do n=$(basename "$d"); run rm -rf "$SRC/$n"; run cp -r "$d" "$SRC/$n"; done
  link() { run ln -sf "$SRC/$1" "$BIN/$2"; }
  link attention/attention attention; link attention/attention waiting-on-me; link attention/attention follow-up; link attention/attention renewals
  link consult/consult consult; link my-messages/my-messages my-messages; link quota/quota-status quota-status; link quota/automode automode
  link efficiency/efficiency efficiency; link skill-review/skill-review skill-review
  link restart-idle/hermes-restart-idle hermes-restart-idle; link artifacts/publish-artifact publish-artifact
  link issues/issue-digest.py issues; link token-stats/token-stats token-stats; link token-stats/tool-output-stats tool-output-stats
  for s in memory-learn/memory-learn:memory-learn.py memory-export/memory-export:memory-export.py kanban-feed/kanban-feed:kanban-feed.py \
           issues/issue-digest.py:issue-digest.py issues/issue-pending.sh:issue-pending.sh approval-notify/approval-notify.py:approval-notify.py \
           gateway-heal/gateway-heal.py:gateway-heal.py quota/quota-guard.py:quota-guard.py maintenance/hermes-backup.sh:hermes-backup.sh \
           maintenance/hermes-update-notice.py:hermes-update-notice.py; do
    run install -m 755 "$SRC/${s%%:*}" "$HH/scripts/${s##*:}"
  done
  [ "$DRY" = 1 ] || printf '#!/bin/sh\nexec /usr/bin/python3 %s/attention/attention check\n' "$SRC" > "$HH/scripts/attention-check.sh"
  [ "$DRY" = 1 ] || printf '#!/bin/sh\nexec /usr/bin/python3 %s/attention/attention pr-resume\n' "$SRC" > "$HH/scripts/pr-resume.sh"
  [ "$DRY" = 1 ] || printf '#!/bin/sh\nexec /usr/bin/python3 %s/skill-review/skill-review\n' "$SRC" > "$HH/scripts/skill-review.sh"
  run mkdir -p "$HOME/agents/skill-proposals"
  run chmod 755 "$HH/scripts/attention-check.sh" "$HH/scripts/pr-resume.sh" "$HH/scripts/skill-review.sh"
  if [ "$DRY" = 0 ]; then  # attention settings: watched domains, and whose "approved" PR comments resume a wait
    mkdir -p "$HOME/agents/attention"
    python3 -c "import json,os,sys
p=sys.argv[3]; c=json.load(open(p)) if os.path.exists(p) else {}
c.update({k: v for k, v in (('domains', sys.argv[1].split()), ('github_owner', sys.argv[2])) if v})
json.dump(c, open(p, 'w'), indent=1)" "${ATTENTION_DOMAINS:-}" "${GITHUB_OWNER:-}" "$HOME/agents/attention/config.json"
  fi
}
step_plugins() {  # every kit plugin into every profile's plugins/ (enabling happens in the config step)
  for p in $(profiles); do h=$(home_of "$p"); run mkdir -p "$h/plugins"
    for d in "$KIT"/plugins/*/; do run rm -rf "$h/plugins/$(basename "$d")"; run cp -r "$d" "$h/plugins/"; done
  done
}
step_patches() {  # local fixes to Hermes; re-run this step after every `hermes update`
  run rm -rf "$SRC/hermes-local-patches"; run cp -r "$KIT/patches" "$SRC/hermes-local-patches"   # the self-check re-verifies them from here
  for p in "$KIT"/patches/*-apply.py; do echo "  $(basename "$p")"; [ "$DRY" = 1 ] || (cd /tmp && "$HPY" "$p" | tail -1) || echo "  ! $(basename "$p") did not apply: check it against your Hermes version"; done
}
step_skills() {  # kit skills: shared ones for every non-locked profile through skills.external_dirs
  run mkdir -p "$HOME/agents/shared-skills"
  for d in "$KIT"/skills/*/; do run rm -rf "$HOME/agents/shared-skills/$(basename "$d")"; run cp -r "$d" "$HOME/agents/shared-skills/"; done
}
step_third_party() { run bash "$SETUP/third-party/install.sh" || echo "  ! some third-party installs failed (see above); continuing"; }
step_config() { "$VENV_PY" "$SETUP/config/apply-overlay.py"; }        # these four print their plan when DRY=1
step_soul() { "$VENV_PY" "$SETUP/soul/apply-sections.py"; }
step_jobs() { "$VENV_PY" "$SETUP/jobs/create-jobs.py"; }
step_brain() { /usr/bin/python3 "$SETUP/brain/setup-brain.py"; }
step_health() { run install -m 755 "$SETUP/health/agent-health.sh" "$HH/scripts/agent-health.sh"; }
step_services() { run sudo bash "$SETUP/services/install-services.sh" "$USER"; }
step_devtools() { run bash "$SETUP/devtools/install-devtools.sh" $INSTALL_DEVTOOLS; }

for s in $STEPS; do
  echo "== $s"
  "step_${s//-/_}"
done
echo "Done. Restart the gateway when idle: hermes-restart-idle (or systemctl restart agent-worker@hermes)."
