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
"$HERMES" plugins install claude-subscription-directsdk --ref 83f0a896b3518c7131181838e340c9a80c79524d --yes-deps --no-enable || echo "  install claude-subscription-directsdk by hand: hermes plugins install --help"
"$HERMES" plugins install holographic --ref 6fe7d424cdc1b197e4a1f2dc1542e9e3869bf4f0 --yes-deps --no-enable || echo "  install holographic by hand (repo itpartypattaya/hermes-plugin-holographic @ 6fe7d42)"

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

echo "== Voice: Hermes's local speech-to-text (faster-whisper) and Edge text-to-speech extras"
# Without them Discord voice joins but never answers: speech arrives, transcription fails and is dropped silently.
# Recorded in Hermes's install facts, so later venv syncs keep them. Runs before the document libraries (it re-syncs the venv).
"$HERMES" pm install --extra edge-tts --extra stt-whisper </dev/null >/dev/null 2>&1 && echo "  ok" || echo "  failed: run hermes pm install --extra edge-tts --extra stt-whisper"
ldconfig -p | grep -q libopus || echo "  Discord voice playback also needs the Opus codec: sudo apt-get install libopus0"

echo "== Document libraries for Hermes's built-in docx/xlsx/powerpoint/pdf skills"
[ -n "$UV" ] && "$UV" pip install -q -p "$VENV_PY" python-docx openpyxl python-pptx pypdf reportlab pdfplumber pypdfium2 && echo "  ok"

echo "== camofox-browser 1.18.1 (browser backend; run it with setup/services/run/camofox.run)"
NODE=$(ls -d "$HH"/tools/node-*/bin 2>/dev/null | tail -1)
mkdir -p "$HOME/camofox" && cd "$HOME/camofox" && [ -f package.json ] || printf '{"dependencies":{"@askjo/camofox-browser":"1.18.1"},"overrides":{"playwright-core":"1.63.0"}}\n' > package.json
PATH="$NODE:$PATH" npm install --no-audit --no-fund >/dev/null 2>&1 && echo "  ok" || echo "  npm install failed in ~/camofox"

echo "== hermes-talk 0.22.1 (realtime voice on the ChatGPT subscription) and memory-wiki (dashboard tab), every profile"
# Talk ships a pyproject.toml named "hermes-talk"; all profiles share one venv workspace, so a second profile's copy
# collides ("Two workspace members are both named hermes-talk"). Profile copies don't need it (its deps are core).
for d in "$HH" "$HH"/profiles/*; do [ -f "$d/config.yaml" ] || continue; n=$(basename "$d"); P=(); [ "$d" = "$HH" ] || P=(-p "$n")
  [ -d "$d/plugins/hermes-talk" ] || "$HERMES" "${P[@]}" plugins install hermes-talk --no-deps </dev/null >/dev/null 2>&1
  [ -d "$d/plugins/memory-wiki" ] || "$HERMES" "${P[@]}" plugins install hermes-memory-wiki --no-deps </dev/null >/dev/null 2>&1
  if [ "$d" != "$HH" ] && [ -f "$d/plugins/hermes-talk/pyproject.toml" ]; then
    mkdir -p "$HOME/agents/src/talk-pyproject-aside/$n" && mv "$d/plugins/hermes-talk/pyproject.toml" "$HOME/agents/src/talk-pyproject-aside/$n/"; fi
  for pl in hermes-talk memory-wiki; do "$HERMES" "${P[@]}" plugins enable "$pl" --no-allow-tool-override </dev/null >/dev/null 2>&1 || echo "  enable $pl in $n failed"; done
  grep -q '^TALK_PROVIDER=' "$d/.env" 2>/dev/null || printf '
# hermes-talk: OpenAI Realtime on the ChatGPT subscription only, never a metered key
TALK_PROVIDER=openai
TALK_PREFER_CODEX_OAUTH=true
' >> "$d/.env"
done
echo "  Discord voice: put TALK_DISCORD_OPERATOR_USER_IDS=<discord ids> in each profile's .env (who may run mutating tools by voice)"

echo "== Agent Reach 1.6.1 (read-only GitHub, YouTube, web, ... for agents); skill linked into Claude Code and every profile"
# uv-managed Python: a system python without ensurepip can't build Agent Reach's private yt-dlp/ffmpeg venvs.
# AGENT_REACH_LANG=en, or its skill is written in Chinese unless the locale starts with en.
AW=agent_reach-1.6.1-py3-none-any.whl
curl -fsSL -o "$T/$AW" "https://github.com/Panniantong/Agent-Reach/releases/download/v1.6.1/$AW"   && echo "6a1085cae53118c5f1271ab24041e55ec17c509932612b919208f04d10183acb  $T/$AW" | sha256sum -c - >/dev/null   && "$UV" tool install -q --force --managed-python --python 3.13 "$T/$AW"   && mkdir -p "$HOME/.agent-reach" && (cd "$HOME" && AGENT_REACH_LANG=en "$HOME/.local/bin/agent-reach" setup </dev/null > "$HOME/.agent-reach/setup.json" 2>&1)   && for s in "$HH"/profiles/*/skills; do [ -e "$s/agent-reach" ] || ln -s "$HOME/.agents/skills/agent-reach" "$s/agent-reach"; done   && echo "  ok" || echo "  agent-reach install failed"
grep -q AGENT_REACH_LANG "$HOME/.profile" 2>/dev/null || echo 'export AGENT_REACH_LANG=en' >> "$HOME/.profile"

echo "== markitdown 0.1.9 (document to Markdown, for the markitdown skill)"
[ -n "$UV" ] && "$UV" tool install -q "markitdown[all]==0.1.9" && echo "  ok"

echo "== Optional web UIs (pinned): run setup/services with webui / workspace / dashboard afterwards"
echo "  git clone https://github.com/nesquena/hermes-webui ~/hermes-webui && git -C ~/hermes-webui checkout v0.52.544"
echo "  git clone https://github.com/outsourc-e/hermes-workspace ~/hermes-workspace && git -C ~/hermes-workspace checkout v2.3.0 && (cd ~/hermes-workspace && pnpm install && pnpm build)"
echo "== Optional hub skills (per profile): hermes -p <profile> skills install skills-sh/supabase/agent-skills/skills/supabase"
echo "   and the Flutter/Dart set: skills-sh/flutter/agent-plugins/skills/<skill>"
