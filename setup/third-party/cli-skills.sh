#!/bin/bash
# Give the coding CLIs (Claude Code, Codex) the skills relevant to coding: files in ~/.agents/skills (Codex reads it),
# a symlink in ~/.claude/skills for Claude Code. Kit team skills are refreshed every run; third-party ones copied once.
HH="$HOME/.hermes"; A="$HOME/.agents/skills"; C="$HOME/.claude/skills"; mkdir -p "$A" "$C"
link() { [ -e "$A/$1" ] && [ ! -e "$C/$1" ] && ln -s "$A/$1" "$C/$1"; return 0; }
for d in "$HOME"/agents/shared-skills-team/*/*/; do
  [ -f "$d/SKILL.md" ] || continue; s=$(basename "$d"); rm -rf "$A/$s"; cp -r "$d" "$A/$s"; link "$s"
done
for s in ast-grep playwright-cli agp-9-upgrade differential-review; do
  src=$(find "$HH"/profiles/*/skills -maxdepth 3 -type d -name "$s" 2>/dev/null | head -1)
  [ -n "$src" ] && [ ! -e "$A/$s" ] && cp -r "$src" "$A/$s"; link "$s"
done
for cat in flutter dart; do   # the Flutter team's official skills, wherever the agents have them
  src=$(find "$HOME/agents/shared-skills/$cat" "$HH"/profiles/*/skills/$cat -maxdepth 0 -type d 2>/dev/null | head -1)
  [ -n "$src" ] || continue
  for d in "$src"/*/; do s=$(basename "$d"); [ -f "$d/SKILL.md" ] || continue; [ -e "$A/$s" ] || cp -r "$d" "$A/$s"; link "$s"; done
done
echo "coding-CLI skills: $(ls "$A" | wc -l) in $A, $(find "$C" -maxdepth 1 -type l | wc -l) linked in $C"
