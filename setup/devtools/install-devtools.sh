#!/bin/bash
# Developer tools for coding agents, each verified against its published checksum where one exists:
#   setup/devtools/install-devtools.sh [claude] [codex] [gh] [flutter] [supabase] [rtk] [context7]
# Installs into ~/.local/opt with links in ~/.local/bin; no sudo. Sign in to each tool yourself afterwards.
set -uo pipefail
OPT=$HOME/.local/opt; BIN=$HOME/.local/bin; mkdir -p "$OPT" "$BIN"
export PATH="$BIN:$(ls -d $HOME/.hermes/tools/node-*/bin 2>/dev/null | tail -1):$PATH"
WANT=" ${*:-claude codex gh} "; want() { case "$WANT" in *" $1 "*) return 0;; esac; return 1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; cd "$T"
latest() { curl -fsSL "https://api.github.com/repos/$1/releases/latest" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"].lstrip("v"))'; }

if want claude; then echo "== Claude Code"
  curl -fsSL https://claude.ai/install.sh -o claude-install.sh && bash claude-install.sh >/dev/null 2>&1; echo "  claude $($BIN/claude --version 2>/dev/null)"; fi
if want codex; then echo "== Codex CLI"
  NPM_CONFIG_PREFIX=$HOME/.local npm install -g --no-audit --no-fund @openai/codex >/dev/null 2>&1; echo "  codex $($BIN/codex --version 2>/dev/null)"; fi
if want gh; then echo "== GitHub CLI"
  GV=$(latest cli/cli)
  curl -fsSL -o gh.tgz "https://github.com/cli/cli/releases/download/v$GV/gh_${GV}_linux_amd64.tar.gz"
  curl -fsSL -o gh.sums "https://github.com/cli/cli/releases/download/v$GV/gh_${GV}_checksums.txt"
  grep "gh_${GV}_linux_amd64.tar.gz" gh.sums | sed "s#gh_${GV}_linux_amd64.tar.gz#gh.tgz#" | sha256sum -c - >/dev/null \
    && mkdir -p "$OPT/gh" && tar -xzf gh.tgz -C "$OPT/gh" --strip-components=1 && echo "  $($OPT/gh/bin/gh --version | head -1)"
  echo "  the kit's bin/gh wrapper calls $OPT/gh/bin/gh with a per-repo sealed token"; fi
if want flutter; then echo "== Flutter (web only)"
  J=$(curl -fsSL https://storage.googleapis.com/flutter_infra_release/releases/releases_linux.json)
  read -r FA FS < <(python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); h=d["current_release"]["stable"]; r=next(x for x in d["releases"] if x["hash"]==h); print(r["archive"], r["sha256"])' <<< "$J")
  curl -fsSL -o flutter.tar.xz "https://storage.googleapis.com/flutter_infra_release/releases/$FA"
  echo "$FS  flutter.tar.xz" | sha256sum -c - >/dev/null && tar -xJf flutter.tar.xz -C "$OPT" && ln -sf "$OPT/flutter/bin/flutter" "$BIN/flutter" && ln -sf "$OPT/flutter/bin/dart" "$BIN/dart"
  flutter --disable-analytics >/dev/null 2>&1; dart --disable-analytics >/dev/null 2>&1
  flutter config --no-analytics --no-enable-android --no-enable-ios --no-enable-linux-desktop --no-enable-macos-desktop --no-enable-windows-desktop >/dev/null 2>&1
  echo "  $(flutter --version 2>/dev/null | head -1)"; fi
if want supabase; then echo "== Supabase CLI"
  SV=$(latest supabase/cli)
  curl -fsSL -o sb.tgz "https://github.com/supabase/cli/releases/download/v$SV/supabase_linux_amd64.tar.gz"
  curl -fsSL -o sb.sums "https://github.com/supabase/cli/releases/download/v$SV/supabase_${SV}_checksums.txt"
  grep " supabase_linux_amd64.tar.gz" sb.sums | sed "s#supabase_linux_amd64.tar.gz#sb.tgz#" | sha256sum -c - >/dev/null \
    && mkdir -p "$OPT/supabase" && tar -xzf sb.tgz -C "$OPT/supabase" && ln -sf "$OPT/supabase/supabase" "$BIN/supabase" && echo "  supabase $($BIN/supabase --version 2>/dev/null)"; fi
if want rtk; then echo "== RTK 1.1.0 (condensed Bash output for Claude Code)"
  # rtk init -g: ~/.claude/RTK.md, an @RTK.md line in ~/.claude/CLAUDE.md, a PreToolUse Bash hook. Telemetry is off by default.
  # The hook rewrites e.g. git status to rtk git status: --dangerously-skip-permissions runs are unaffected, an interactive
  # claude in normal permission mode asks before running the rewritten command. rtk bypass <cmd> runs one raw.
  RB=https://github.com/rtk-ai/rtk/releases/download/v1.1.0
  curl -fsSLO "$RB/rtk-x86_64-unknown-linux-musl.tar.gz" && curl -fsSLO "$RB/checksums.txt"     && grep " rtk-x86_64-unknown-linux-musl.tar.gz$" checksums.txt | sha256sum -c - >/dev/null && tar -xzf rtk-x86_64-unknown-linux-musl.tar.gz     && install -m 755 rtk "$BIN/rtk" && "$BIN/rtk" init -g --auto-patch </dev/null >/dev/null 2>&1 && echo "  $($BIN/rtk --version), hooked into Claude Code"; fi
if want context7; then echo "== Context7 (library docs MCP) for Claude Code"
  "$BIN/claude" mcp get context7 >/dev/null 2>&1 || "$BIN/claude" mcp add --scope user --transport http context7 https://mcp.context7.com/mcp </dev/null >/dev/null 2>&1
  "$BIN/claude" mcp get context7 >/dev/null 2>&1 && echo "  ok (no key: lower rate limit; a free key from context7.com raises it)"; fi
