#!/bin/bash
# sudo setup/services/install-services.sh <user> [service...]   (default: hermes)
# Installs the agent-worker@ template, copies the chosen run scripts to ~<user>/agents/<service>/run, writes a
# credentials drop-in naming the sealed credentials each one reads, and enables the services. Seal the credentials
# first (README: "Secrets"), or the service won't start.
set -euo pipefail
U=$1; shift; SVCS=${*:-hermes}; HOMEDIR=$(getent passwd "$U" | cut -d: -f6); HERE=$(cd "$(dirname "$0")" && pwd)
sed "s#__USER__#$U#; s#__HOME__#$HOMEDIR#g" "$HERE/agent-worker@.service.template" > /etc/systemd/system/agent-worker@.service
declare -A CREDS=([hermes]="discord_bot_token" [webui]="ui_password" [workspace]="hermes_api_key ui_password" [camofox]="ui_password" [dashboard]="" [vaultwarden]="")
for s in $SVCS; do
  install -d -o "$U" -g "$U" "$HOMEDIR/agents/$s"
  install -m 755 -o "$U" -g "$U" "$HERE/run/$s.run" "$HOMEDIR/agents/$s/run"
  if [ -n "${CREDS[$s]:-}" ]; then
    install -d "/etc/systemd/system/agent-worker@$s.service.d"
    { echo "[Service]"; for c in ${CREDS[$s]}; do echo "LoadCredentialEncrypted=$c"; done; } > "/etc/systemd/system/agent-worker@$s.service.d/credentials.conf"
  fi
done
systemctl daemon-reload
for s in $SVCS; do systemctl enable --now "agent-worker@$s" && echo "agent-worker@$s: $(systemctl is-active agent-worker@$s)"; done
