#!/bin/bash
# One-time OAuth logins for the Supabase and Cloudflare connectors (Hermes and Codex CLI) on this VM: one login per
# connector, shared by every Hermes profile through ~/.hermes/shared-mcp-tokens. Run from your PC so the browser
# callback reaches the VM, and do one VM at a time (both use local port 8765):
#   ssh -t -L 8765:127.0.0.1:8765 <user>@<vm> bash ~/agents/src/mcp-setup/login-all.sh
# Open each printed URL in your browser, sign in if asked, approve. Already-logged-in connectors are skipped.
export PATH=$HOME/.local/bin:$PATH
bash $HOME/agents/src/mcp-setup/share-tokens.sh >/dev/null
S=$HOME/.hermes/shared-mcp-tokens
for s in supabase cloudflare; do
  p=""
  for d in $HOME/.hermes/profiles/*; do   # prefer the read-write (devops) profile for the login itself
    grep -A3 "^  $s:" $d/config.yaml 2>/dev/null | grep -q "auth: oauth" || continue
    [ -z "$p" ] || [[ $(basename $d) == *-devops ]] && p=$(basename $d)
  done
  [ -n "$p" ] || continue
  if [ -s $S/$s.json ]; then echo "Hermes $s: already logged in"; continue; fi
  echo; echo "== Hermes $s (shared by all profiles that use it; logging in as $p)"
  hermes -p "$p" mcp login "$s"
done
for s in supabase cloudflare; do
  codex mcp list 2>/dev/null | grep "^$s " | grep -q "Not logged in" || continue
  echo; echo "== Codex CLI $s"; codex mcp login "$s" --no-browser
done
echo; echo "Done. Tell Claude 'logins done' so it restarts the gateway when idle and tests the connectors."
