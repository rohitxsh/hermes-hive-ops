"""Append the kit's SOUL sections (sections/*.md, in file order) to every profile's SOUL.md that doesn't have them yet,
with {OWNER} filled in. Locked profiles get only sections marked `<!-- locked-ok -->`. If the i-have-adhd skill is
installed (setup/third-party), its rules are added as an always-on reply-format section. Backs up SOUL.md once
(SOUL.md.bak-kit). DRY=1 prints what would be added."""
import glob
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
HH = os.path.expanduser("~/.hermes")
DRY = os.environ.get("DRY") == "1"
OWNER = os.environ.get("OWNER_NAME") or "the owner"
LOCKED = set(os.environ.get("LOCKED_PROFILES", "").split())

sections = []
for f in sorted(glob.glob(f"{HERE}/sections/*.md")):
    raw = open(f, encoding="utf-8").read().strip().replace("{OWNER}", OWNER)
    text = raw.replace("<!-- locked-ok -->\n", "")
    sections.append((text.splitlines()[0].strip(), text, "<!-- locked-ok -->" in raw))
adhd = sorted(glob.glob(os.path.expanduser("~/agents/shared-skills/i-have-adhd/SKILL.md")))
if adhd:
    body = re.sub(r"\A---\n.*?\n---\n", "", open(adhd[0], encoding="utf-8").read(), flags=re.S).strip()
    body = re.sub(r"\A# i-have-adhd\n+", "", body)
    body = re.sub(r"^(#{2,3}) ", lambda m: "#" + m.group(1) + " ", body, flags=re.M)
    head = "## Reply format: i-have-adhd (always on)"
    sections.append((head, f"{head}\nEvery reply follows the rules below by default (source: the i-have-adhd skill, already loaded here, "
                           "so don't load it again). \"stop adhd mode\" or \"normal mode\" turns it off for that conversation only. "
                           "Formats other sections or tools require keep their content; give them this shape.\n\n" + body, True))

for p in [f"{HH}/SOUL.md"] + sorted(glob.glob(f"{HH}/profiles/*/SOUL.md")):
    name = "default" if os.path.dirname(p) == HH else os.path.basename(os.path.dirname(p))
    soul = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    add = [t for head, t, ok in sections if head not in soul and (ok or name not in LOCKED)]
    print(f"{name}: {len(add)} section(s) " + ("would be added" if DRY else "added"))
    if add and not DRY:
        if os.path.exists(p) and not os.path.exists(p + ".bak-kit"):
            shutil.copy2(p, p + ".bak-kit")
        open(p, "w", encoding="utf-8").write((soul.rstrip("\n") + "\n\n" if soul.strip() else "") + "\n\n".join(add) + "\n")
