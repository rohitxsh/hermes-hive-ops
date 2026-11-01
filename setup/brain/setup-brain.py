"""Set up ~/brain, the owner's long-term notes on this machine: plain Markdown in a local git repo (never pushed).
One area file per profile (notes/<profile>.md); PRIVATE_PROFILES write to notes/private/<profile>.md (mode 700);
LOCKED_PROFILES never file. memory-learn files decisions and preferences into it nightly and commits.
about.md is seeded once from the profiles' USER.md. Idempotent. /usr/bin/python3."""
import glob
import json
import os
import subprocess

H = os.path.expanduser("~")
HH = f"{H}/.hermes"
B = f"{H}/brain"
DRY = os.environ.get("DRY") == "1"
OWNER = os.environ.get("OWNER_NAME") or "the owner"
LOCKED = set(os.environ.get("LOCKED_PROFILES", "").split())
PRIVATE = set(os.environ.get("PRIVATE_PROFILES", "").split())

names = ["default"] + sorted(os.path.basename(d) for d in glob.glob(f"{HH}/profiles/*") if os.path.isfile(f"{d}/config.yaml"))
areas = {n: (f"private/{n}" if n in PRIVATE else n) for n in names if n not in LOCKED}
if DRY:
    print("would set up ~/brain with areas", areas, "skip", sorted(LOCKED))
    raise SystemExit
os.makedirs(f"{B}/notes", mode=0o700, exist_ok=True)
os.chmod(B, 0o700)
if PRIVATE:
    os.makedirs(f"{B}/notes/private", mode=0o700, exist_ok=True)
json.dump({"areas": areas, "skip": sorted(LOCKED)}, open(f"{B}/.areas.json", "w"), indent=1)
if not os.path.exists(f"{B}/README.md"):
    open(f"{B}/README.md", "w").write(
        f"# Second brain\n\n{OWNER}'s long-term notes on this machine: decisions and their reasons, preferences, lasting facts.\n"
        "Plain Markdown in a local git repo (never pushed): `git log -p` shows who filed what, `git revert` undoes it.\n\n"
        "- `about.md`: who these notes are for.\n- `notes/<area>.md`: one dated line per item, `- YYYY-MM-DD (profile): text`.\n"
        "- `.areas.json`: profile -> area; `skip` never files.\n\n"
        "Agents append when someone says \"note: ...\"; memory-learn files from chats every night and commits.\n"
        "Corrections are new lines; nothing is edited in place; no secrets.\n")
if not os.path.exists(f"{B}/about.md"):
    seen, lines = set(), []
    for n in names:
        if n in LOCKED or n in PRIVATE:
            continue
        p = f"{HH}/memories/USER.md" if n == "default" else f"{HH}/profiles/{n}/memories/USER.md"
        for e in (open(p, encoding="utf-8").read().split("§") if os.path.exists(p) else []):
            e = " ".join(e.split())
            if e and e not in seen:
                seen.add(e)
                lines.append(f"- {e}")
    open(f"{B}/about.md", "w", encoding="utf-8").write(f"# About {OWNER}\n\n" + ("\n".join(lines) or "- (nothing yet)") + "\n")
for a in set(areas.values()):
    p = f"{B}/notes/{a}.md"
    if not os.path.exists(p):
        open(p, "w").write(f"# {os.path.basename(a)} notes\n\n")
git = ["git", "-C", B]
if not os.path.isdir(f"{B}/.git"):
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["config", "user.name", "brain"], check=True)
    subprocess.run(git + ["config", "user.email", "brain@localhost"], check=True)
if subprocess.run(git + ["status", "--porcelain"], capture_output=True, text=True).stdout.strip():
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "second brain set up"], check=True)
print("~/brain ready:", len(areas), "areas")
