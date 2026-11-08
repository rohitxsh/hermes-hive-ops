#!/bin/bash
# Daily Hermes backup (Hermes cron "hermes backup", 02:30, no LLM): every profile's config, skills,
# sessions, memory, cron jobs, .env and logins, zipped to ~/hermes-backups (keeps 7; 2 once a backup-drive copy exists) plus a copy on the
# backup drive (below). It runs before a nightly VM or disk backup, so that image holds it too.
# Restore: `hermes import <zip>`.
# Archives contain logins; protect partial and failed writes, not just success.
umask 077
# Silent when it works; on failure prints the error (posted by Hermes as a failure notice).
export PATH="$HOME/.local/bin:$PATH"
dir="$HOME/hermes-backups"; mkdir -p "$dir"; chmod 700 "$dir"
zip="$dir/hermes-backup-$(date +%F).zip"
if ! out=$(hermes backup -o "$zip" -k 7 2>&1); then
  echo "Hermes backup failed: $(printf '%s' "$out" | grep -v 'Command helper' | tail -3)"; exit 1
fi
chmod 600 "$dir"/hermes-backup-*.zip  # the zip holds .env files and logins
[ -s "$zip" ] || { echo "Hermes backup produced no file at $zip"; exit 1; }
# Second copy on the backup drive (a separate disk, e.g. the host's USB HDD) when one is mounted, so a restore
# doesn't need the VM image. Same 7-day retention. Set HERMES_BACKUP_COPY_DIR to use another mount.
ext=${HERMES_BACKUP_COPY_DIR:-/mnt/ext-backup}
if mountpoint -q "$ext" && [ -w "$ext" ]; then
  mkdir -p "$ext/hermes-backups" && chmod 700 "$ext/hermes-backups" && cp "$zip" "$ext/hermes-backups/" \
    && chmod 600 "$ext/hermes-backups/${zip##*/}" || { echo "Hermes backup: copy to $ext failed"; exit 1; }
  ls -1t "$ext"/hermes-backups/hermes-backup-*.zip | tail -n +8 | xargs -r rm -f --
  # the 7-day history now lives on the backup drive; keep only the newest 2 on the VM disk, so the nightly VM image
  # (which already includes this disk) doesn't carry seven more copies of the same data
  ls -1t "$dir"/hermes-backup-*.zip | tail -n +3 | xargs -r rm -f --
fi
