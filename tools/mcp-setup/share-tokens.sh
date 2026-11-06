#!/bin/bash
# One OAuth login per connector per machine: every profile with an OAuth MCP connector gets its mcp-tokens folder
# linked to ~/.hermes/shared-mcp-tokens (Hermes keeps its refresh lock next to the token, so the profiles share
# that lock too). A profile's existing complete login (token + client) is kept; leftovers go to ~/agents/retired/.
# Idempotent. Read-only vs read-write stays per profile in its url (`read_only=true`).
S=$HOME/.hermes/shared-mcp-tokens; R=$HOME/agents/retired/mcp-tokens-$(date +%F); mkdir -p $S; chmod 700 $S
for d in $HOME/.hermes/profiles/*; do
  grep -q "auth: oauth" $d/config.yaml 2>/dev/null || continue
  t=$d/mcp-tokens
  [ -L $t ] && continue
  if [ -d $t ]; then
    for tok in $t/*.json; do
      [ -e "$tok" ] || continue
      case $tok in *.client.json|*.meta.json) continue;; esac
      base=${tok%.json}
      # a complete login (tokens + client) moves into the shared folder unless one is already there
      if [ ! -e $S/$(basename $tok) ] && [ -e $base.client.json ]; then mv $base.* $S/ 2>/dev/null; fi
    done
    if [ -n "$(ls -A $t 2>/dev/null)" ]; then mkdir -p $R/$(basename $d); mv $t/* $t/.[!.]* $R/$(basename $d)/ 2>/dev/null; fi
    rmdir $t
  fi
  ln -s $S $t
  echo "linked $(basename $d)"
done
echo "shared logins: $(cd $S && ls *.json 2>/dev/null | grep -v '\.client\.json\|\.meta\.json' | tr '\n' ' ')"
