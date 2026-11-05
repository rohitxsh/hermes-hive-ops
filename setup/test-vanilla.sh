#!/bin/bash
# Install this kit into a throwaway HOME that holds vanilla Hermes (git HEAD of your checkout, so no local patches),
# then check the result. Changes nothing in your real ~/.hermes. Needs Hermes installed from git and ~1 GB in TMPDIR.
#   setup/test-vanilla.sh           run it; exit 0 when every check passes
# Skips third-party, services and devtools (downloads and sudo).
set -uo pipefail
KIT=$(cd "$(dirname "$0")/.." && pwd)
REAL=$HOME
T=$(mktemp -d "${TMPDIR:-/tmp}/kit-vanilla.XXXXXX")
trap 'rm -rf "$T"' EXIT
fail=0; check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }

mkdir -p "$T/.hermes/hermes-agent" "$T/.local/bin"
git -C "$REAL/.hermes/hermes-agent" archive HEAD | tar -x -C "$T/.hermes/hermes-agent"
ln -s "$REAL/.hermes/installs" "$T/.hermes/installs"; ln -s "$REAL/.hermes/tools" "$T/.hermes/tools"
V=$(python3 -c "import json,glob;f=sorted(glob.glob('$REAL/.hermes/installs/*/facts.json'))[-1];print(json.load(open(f))['packages']['venv']['environment'])")
printf '#!/bin/sh\nPYTHONPATH=%s exec %s -c "import sys; from hermes_cli.main import main; sys.argv[0]=\\"hermes\\"; sys.exit(main())" "$@"\n' \
  "$T/.hermes/hermes-agent" "$V/bin/python" > "$T/.local/bin/hermes"
chmod 755 "$T/.local/bin/hermes"
export HOME=$T PATH=$T/.local/bin:/usr/local/bin:/usr/bin:/bin
cd "$T"
hermes config set model.default test-model >/dev/null 2>&1
hermes profile create alpha >/dev/null 2>&1; hermes profile create webonly >/dev/null 2>&1
cp -r "$KIT" "$T/kit"
cat > "$T/kit/setup/settings.env" <<'EOF'
OWNER_NAME="Sam"
OWNER_CHAT_USER_ID="100000000000000001"
ADMIN_DELIVER=""
ADMIN_PROFILE="default"
LOCKED_PROFILES="webonly"
PRIVATE_PROFILES="alpha"
GITHUB_OWNER="example-owner"
ATTENTION_DOMAINS="example.com"
INSTALL_DEVTOOLS=""
EOF
STEPS=bin,tools,plugins,patches,skills,config,soul,health,jobs,brain
echo "== install (twice, to check it is idempotent)"
check "first run exits 0" "bash '$T/kit/setup/install.sh' --steps $STEPS > '$T/run1.log' 2>&1"
cp "$T/.hermes/SOUL.md" "$T/soul1"
check "second run exits 0" "bash '$T/kit/setup/install.sh' --steps $STEPS > '$T/run2.log' 2>&1"
check "SOUL unchanged by the second run" "cmp -s '$T/soul1' '$T/.hermes/SOUL.md'"
echo "== result"
for p in "$T"/kit/patches/*-apply.py; do grep -q '"--check"' "$p" || continue
  check "patch $(basename "$p")" "(cd /tmp && '$V/bin/python' '$p' --check >/dev/null 2>&1)"; done
for c in attention efficiency skill-review kanban-doctor pending-human; do check "$c self-test" "$c --selftest >/dev/null 2>&1"; done
check "ops-core self-test" "python3 -I '$T/.hermes/plugins/ops-core/__init__.py' --selftest >/dev/null 2>&1"
check "ops-core in every profile" "( for d in '$T/.hermes' '$T'/.hermes/profiles/*; do [ -f \"\$d/plugins/ops-core/__init__.py\" ] || exit 1; done )"
check "shared SOUL rules applied" "hermes ops-rules check 2>/dev/null | grep -q 'would update 0 SOUL'"
check "hermes ops runs a kit tool" "hermes ops doctor --selftest >/dev/null 2>&1"
check "efficiency runs on an empty home" "efficiency --days 1 >/dev/null 2>&1"
jobs=$(hermes cron list 2>&1 | grep -c "Name:")
check "14 maintenance jobs created ($jobs)" "[ '$jobs' -ge 14 ]"
check "locked profile has no shared skills" "grep -q 'external_dirs: \[\]' '$T/.hermes/profiles/webonly/config.yaml'"
check "self-check is silent" "[ -z \"\$(bash '$T/.hermes/scripts/agent-health.sh' 2>&1)\" ]"
[ $fail = 0 ] && echo "All checks passed." || { echo "Some checks failed; logs were in $T (removed on exit; rerun with 'trap - EXIT' to keep them)."; }
exit $fail
