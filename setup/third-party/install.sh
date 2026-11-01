#!/bin/bash
# Third-party pieces this setup uses, at the versions it was tested with. Nothing here is copied into the kit;
# each comes from its own source. Re-running is safe. Review each project before installing it on your machine.
set -uo pipefail
HH="$HOME/.hermes"; SK="$HOME/agents/shared-skills"; mkdir -p "$SK"
HERMES="$HOME/.local/bin/hermes"
VENV_PY=$(python3 -c "import json,glob,os;f=sorted(glob.glob(os.path.expanduser('~/.hermes/installs/*/facts.json')),key=os.path.getmtime)[-1];print(json.load(open(f))['packages']['venv']['environment']+'/bin/python')")
UV=$(ls -d "$HH"/tools/uv-*/uv 2>/dev/null | tail -1)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
pin() { git clone -q "$1" "$T/$2" && git -C "$T/$2" -c advice.detachedHead=false checkout -q "$3"; }

echo "== Hermes plugins (official and community catalog, pinned)"
"$HERMES" plugins install claude-subscription-directsdk --ref 54afaf5014db23346148436c4883eb64095e8060 --yes-deps --no-enable || echo "  install claude-subscription-directsdk by hand: hermes plugins install --help"
"$HERMES" plugins install holographic --ref b81f060937ef230759fa171a7e2ea209e84b0a60 --yes-deps --no-enable || echo "  install holographic by hand (repo itpartypattaya/hermes-plugin-holographic @ b81f060)"

echo "== Shared skills (pinned upstream commits)"
pin https://github.com/ayghri/i-have-adhd adhd 1ecea19 && rm -rf "$SK/i-have-adhd" && cp -r "$T/adhd/skills/i-have-adhd" "$SK/" && cp "$T/adhd/LICENSE" "$SK/i-have-adhd/"
pin https://github.com/anthropics/knowledge-work-plugins kwp 2574e29 && rm -rf "$SK/data-visualization" && cp -r "$T/kwp/data/skills/data-visualization" "$SK/" && cp "$T/kwp/LICENSE" "$SK/data-visualization/"
pin https://github.com/cloudflare/security-audit-skill sas c1c8a8c && rm -rf "$SK/security-audit" && cp -r "$T/sas/skills/security-audit" "$SK/" && cp "$T/sas/LICENSE" "$SK/security-audit/"
# Anthropic's frontend-design: from the Claude Code plugin cache when Claude Code has it installed
FD=$(ls -d "$HOME"/.claude/plugins/cache/claude-plugins-official/frontend-design/*/skills/frontend-design 2>/dev/null | tail -1)
[ -n "$FD" ] && { rm -rf "$SK/frontend-design"; cp -r "$FD" "$SK/"; } || echo "  frontend-design: install Claude Code's frontend-design plugin first (setup/devtools), then re-run"

echo "== obra/superpowers Hermes plugin (pinned) without its session-start injection"
for d in "$HH" "$HH"/profiles/*; do [ -f "$d/config.yaml" ] || continue
  [ -d "$d/plugins/superpowers" ] || git clone -q https://github.com/obra/superpowers.git "$d/plugins/superpowers"
  git -C "$d/plugins/superpowers" -c advice.detachedHead=false checkout -q 2ce8aa15
done
echo "  then: python $HOME/agents/src/speed-tune/tune.py --dry-run (and without --dry-run) to drop its injection and prune unused skills"

echo "== Document libraries for Hermes's built-in docx/xlsx/powerpoint/pdf skills"
[ -n "$UV" ] && "$UV" pip install -q -p "$VENV_PY" python-docx openpyxl python-pptx pypdf reportlab pdfplumber pypdfium2 && echo "  ok"

echo "== camofox-browser 1.18.1 (browser backend; run it with setup/services/run/camofox.run)"
NODE=$(ls -d "$HH"/tools/node-*/bin 2>/dev/null | tail -1)
mkdir -p "$HOME/camofox" && cd "$HOME/camofox" && [ -f package.json ] || printf '{"dependencies":{"@askjo/camofox-browser":"1.18.1"},"overrides":{"playwright-core":"1.63.0"}}\n' > package.json
PATH="$NODE:$PATH" npm install --no-audit --no-fund >/dev/null 2>&1 && echo "  ok" || echo "  npm install failed in ~/camofox"

echo "== markitdown 0.1.9 (document to Markdown, for the markitdown skill)"
[ -n "$UV" ] && "$UV" tool install -q "markitdown[all]==0.1.9" && echo "  ok"

echo "== Optional web UIs (pinned): run setup/services with webui / workspace / dashboard afterwards"
echo "  git clone https://github.com/nesquena/hermes-webui ~/hermes-webui && git -C ~/hermes-webui checkout v0.52.544"
echo "  git clone https://github.com/outsourc-e/hermes-workspace ~/hermes-workspace && git -C ~/hermes-workspace checkout v2.3.0 && (cd ~/hermes-workspace && pnpm install && pnpm build)"
echo "== Optional hub skills (per profile): hermes -p <profile> skills install skills-sh/supabase/agent-skills/skills/supabase"
echo "   and the Flutter/Dart set: skills-sh/flutter/agent-plugins/skills/<skill>"
