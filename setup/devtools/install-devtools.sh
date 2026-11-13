#!/bin/bash
# Developer tools for coding agents, each verified against its published checksum where one exists:
#   setup/devtools/install-devtools.sh [claude] [codex] [gh] [flutter] [supabase] [rtk] [context7] [presentations] [android-test] [k6]
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
  NPM_CONFIG_PREFIX=$HOME/.local npm install -g --no-audit --no-fund @openai/codex@latest >/dev/null 2>&1
  if ! command -v node >/dev/null && NB=$(ls -d "$HOME"/.hermes/tools/node-*/bin 2>/dev/null | sort -V | tail -1); then
    # no system node: npm's symlink to codex.js can't run, so launch it with Hermes's bundled node (rm the link first:
    # writing through it would overwrite codex.js)
    rm -f "$BIN/codex"; printf '%s\n' '#!/bin/sh' "exec \"$NB/node\" \"$HOME/.local/lib/node_modules/@openai/codex/bin/codex.js\" \"\$@\"" > "$BIN/codex"
    chmod 755 "$BIN/codex"
  fi
  echo "  codex $($BIN/codex --version 2>/dev/null)"; fi
if want presentations; then echo "== Presentations (Marp CLI; LibreOffice and poppler render slides for checking)"
  NPM_CONFIG_PREFIX=$HOME/.local npm install -g --no-audit --no-fund @marp-team/marp-cli@4 >/dev/null 2>&1
  # Marp renders with Chrome: point it at Hermes's own Chromium
  printf '%s\n' '#!/bin/sh' 'CHROME_PATH=$(ls -d "$HOME"/.hermes/tools/chromium-*/chrome-linux64/chrome 2>/dev/null | sort -V | tail -1)' \
    'export CHROME_PATH' 'exec "$HOME/.local/lib/node_modules/.bin/marp" "$@"' > "$BIN/marp"; chmod 755 "$BIN/marp"
  echo "  $($BIN/marp --version 2>/dev/null | head -1)"
  command -v soffice >/dev/null && command -v pdftoppm >/dev/null || echo "  for slide rendering also run: sudo apt-get install --no-install-recommends libreoffice-impress poppler-utils fonts-liberation fonts-dejavu-core fonts-noto-core"
fi
if want android-test; then echo "== Android test phone (SDK, emulator, AVD agents_api34) + Maestro"
  java -version 2>&1 | grep -qE 'version "(1[7-9]|2[0-9])' || echo "  needs Java 17+: sudo apt-get install --no-install-recommends openjdk-17-jdk-headless"
  SDK=$OPT/android-sdk
  if [ ! -x "$SDK/cmdline-tools/latest/bin/sdkmanager" ]; then
    url=$(curl -fsSL https://developer.android.com/studio | grep -oE 'https://dl.google.com/android/repository/commandlinetools-linux-[0-9]+_latest.zip' | head -1)
    curl -fsSL -o clt.zip "$url" && unzip -q clt.zip && mkdir -p "$SDK/cmdline-tools" && rm -rf "$SDK/cmdline-tools/latest" && mv cmdline-tools "$SDK/cmdline-tools/latest"
  fi
  yes | "$SDK/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$SDK" --licenses >/dev/null 2>&1
  "$SDK/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$SDK" platform-tools emulator "system-images;android-34;google_apis;x86_64" >/dev/null 2>&1
  ln -sf "$SDK/platform-tools/adb" "$BIN/adb"
  "$SDK/cmdline-tools/latest/bin/avdmanager" list avd 2>/dev/null | grep -q "Name: agents_api34" || echo no |     "$SDK/cmdline-tools/latest/bin/avdmanager" create avd -n agents_api34 -k "system-images;android-34;google_apis;x86_64" -d pixel_6 >/dev/null 2>&1
  MV=$(latest mobile-dev-inc/maestro)   # tags look like cli-2.12.1
  curl -fsSL -o maestro.zip "https://github.com/mobile-dev-inc/maestro/releases/download/$MV/maestro.zip" \
    && curl -fsSL -o maestro.sums "https://github.com/mobile-dev-inc/maestro/releases/download/$MV/checksums_sha256.txt" \
    && grep " maestro.zip$" maestro.sums | sha256sum -c - >/dev/null && unzip -q maestro.zip \
    && rm -rf "$OPT/maestro" && mv maestro "$OPT/maestro" && ln -sf "$OPT/maestro/bin/maestro" "$BIN/maestro" \
    || echo "  maestro download or checksum failed; not installed"
  [ -e /dev/kvm ] || echo "  no /dev/kvm: the emulator needs hardware virtualisation (enable nested virtualisation for this VM)"
  echo "  maestro $(MAESTRO_CLI_NO_ANALYTICS=1 $BIN/maestro --version 2>/dev/null | tail -1); start a phone with: android-emulator up"
fi
if want k6; then echo "== k6 (load testing)"
  KV=$(latest grafana/k6); f="k6-v$KV-linux-amd64.tar.gz"
  curl -fsSL -o "$f" "https://github.com/grafana/k6/releases/download/v$KV/$f" && curl -fsSL -o k6.sums "https://github.com/grafana/k6/releases/download/v$KV/k6-v$KV-checksums.txt"
  grep " $f\$" k6.sums | sha256sum -c - >/dev/null && tar -xzf "$f" && mkdir -p "$OPT/k6" && mv "k6-v$KV-linux-amd64/k6" "$OPT/k6/k6" && ln -sf "$OPT/k6/k6" "$BIN/k6"
  echo "  $($BIN/k6 version 2>/dev/null | head -1)"
fi
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
