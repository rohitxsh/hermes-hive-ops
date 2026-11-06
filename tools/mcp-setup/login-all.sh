#!/bin/bash
# One-time OAuth logins for the Supabase and Cloudflare connectors (Hermes profiles and Codex CLI) on this VM.
# Run from your PC so the browser callback reaches the VM:
#   ssh -t -L 8765:127.0.0.1:8765 <user>@<vm> bash ~/agents/src/mcp-setup/login-all.sh
# For each step: open the printed URL in your browser, sign in if asked, approve. Already-logged-in steps are skipped.
export PATH=$HOME/.local/bin:$PATH
steps=()
for d in $HOME/.hermes/profiles/*; do
  p=$(basename $d)
  for s in supabase cloudflare; do
    grep -A3 "^  $s:" $d/config.yaml 2>/dev/null | grep -q "auth: oauth" && steps+=("hermes $p $s")
  done
done
for s in supabase cloudflare; do codex mcp list 2>/dev/null | grep -q "^$s " && steps+=("codex - $s"); done
n=${#steps[@]}; i=0
for st in "${steps[@]}"; do
  set -- $st; i=$((i+1))
  if [ "$1" = codex ]; then
    codex mcp list 2>/dev/null | grep "^$3 " | grep -q "Not logged in" || { echo "[$i/$n] Codex $3: already logged in"; continue; }
    echo; echo "[$i/$n] Codex CLI -> $3"; codex mcp login "$3" --no-browser
  else
    [ -s "$HOME/.hermes/profiles/$2/mcp-tokens/$3.json" ] && { echo "[$i/$n] $2 $3: already logged in"; continue; }
    echo; echo "[$i/$n] Hermes profile $2 -> $3"; hermes -p "$2" mcp login "$3"
  fi
done
echo; echo "Done. Tell Claude 'logins done' so it restarts the gateway when idle and tests the connectors."
