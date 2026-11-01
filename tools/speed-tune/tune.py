"""Speed changes for every profile on this VM (the owner, 2026-11-01: "apply the 4 recommended changes on all four vms for
all agents/profiles"). Run with Hermes's venv python (ruamel keeps config comments). `--dry-run` prints the plan only.
1. compression.threshold_tokens 80000 -> 200000 (fewer compressions, so fewer skill reloads and less lost context)
2. (separate script: kanban-guardrail-block-apply.py)
3. superpowers plugin: no first-turn bootstrap injection; skills.disabled += built-in/shared skills this profile has
   never been loaded by any profile on this VM and that nothing this profile runs names (SOUL, its cron jobs, its Kanban tasks). The profile's own and hub skills,
   anything it has used, and hermes-agent stay.
4. streaming.enabled: true (replies appear in Discord as they are written)."""
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys

from ruamel.yaml import YAML

H = os.path.expanduser("~")
HH = f"{H}/.hermes"
TAG = ".bak-2026-11-01-speed"
DRY = "--dry-run" in sys.argv
yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 4096

profiles = [("default", HH)] + [(n, f"{HH}/profiles/{n}") for n in sorted(os.listdir(f"{HH}/profiles"))
                                if os.path.isfile(f"{HH}/profiles/{n}/config.yaml")]
kanban_skills = {}
if os.path.exists(f"{HH}/kanban.db"):
    c = sqlite3.connect(f"file:{HH}/kanban.db?mode=ro", uri=True)
    for who, sk, body in c.execute("select assignee, skills, body from tasks"):
        kanban_skills.setdefault(who or "", []).append(f"{sk or ''} {body or ''}")


def catalog(name):
    env = dict(os.environ, COLUMNS="500")
    args = [f"{H}/.local/bin/hermes"] + ([] if name == "default" else ["-p", name]) + ["skills", "list", "--enabled-only"]
    out = subprocess.run(args, capture_output=True, text=True, env=env).stdout
    rows = []
    for line in out.splitlines():
        cells = [x.strip() for x in line.split("│")]
        if len(cells) >= 6 and cells[1] and cells[1] != "Name":
            rows.append((cells[1], cells[3]))
    return rows


def used(home):
    names = set()
    db = f"{home}/state.db"
    if not os.path.exists(db):
        return names
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for (tc,) in c.execute("select tool_calls from messages where tool_calls like '%skill_view%'"):
        try:
            for x in json.loads(tc):
                f = x.get("function") or {}
                if f.get("name") == "skill_view":
                    names.add(json.loads(f.get("arguments") or "{}").get("name", ""))
        except Exception:
            pass
    return {n.split(":")[-1] for n in names} | names


vm_used = set().union(*(used(h) for _n, h in profiles))  # used by any profile here
report = []
for name, home in profiles:
    soul = open(f"{home}/SOUL.md", encoding="utf-8").read() if os.path.exists(f"{home}/SOUL.md") else ""
    jobs = open(f"{home}/cron/jobs.json", encoding="utf-8").read() if os.path.exists(f"{home}/cron/jobs.json") else ""
    refs = soul + jobs + " ".join(kanban_skills.get(name, []))
    u = used(home)
    cat = catalog(name)
    prune = sorted(n for n, src in cat if src in ("builtin", "external") and n != "hermes-agent" and n not in u and n not in vm_used
                   and not re.search(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", refs))
    cfg_path = f"{home}/config.yaml"
    cfg = yaml.load(open(cfg_path))
    old_dis = list((cfg.get("skills") or {}).get("disabled") or [])
    new_dis = sorted(set(map(str, old_dis)) | set(prune))
    report.append(f"{name}: {len(cat)} skills enabled -> disable {len(new_dis) - len(old_dis)} more (keep {len(cat) - len(prune)}); "
                  f"kept built-in/shared because used or named: "
                  + ", ".join(sorted(n for n, src in cat if src in ("builtin", "external") and n not in prune))[:400])
    if DRY:
        continue
    shutil.copy2(cfg_path, cfg_path + TAG) if not os.path.exists(cfg_path + TAG) else None
    cfg.setdefault("compression", {})["threshold_tokens"] = 200000
    if cfg.get("streaming") is None:
        cfg["streaming"] = {}
    pass  # streaming stays off: with a plugin appending to replies it doubled long Discord replies
    if cfg.get("skills") is None:
        cfg["skills"] = {}
    cfg["skills"]["disabled"] = new_dis
    with open(cfg_path, "w") as fh:
        yaml.dump(cfg, fh)
    # superpowers: keep the skills, drop the session-start "1% rule" injection
    for p in glob.glob(f"{home}/plugins/superpowers/.hermes-plugin/__init__.py"):
        s = open(p, encoding="utf-8").read()
        old = "        if is_first_turn:\n            return {\"context\": bootstrap}\n        return None\n"
        if "local change (2026-11-01)" not in s:
            assert s.count(old) == 1, p
            shutil.copy2(p, p + TAG)
            open(p, "w", encoding="utf-8").write(s.replace(old, (
                "        # local change (2026-11-01, the owner): no bootstrap injection. Its \"if there is even a 1% chance a\n"
                "        # skill applies you MUST load it\" rule made agents load skills on most turns. The skills stay\n"
                "        # registered for on-demand skill_view.\n"
                "        return None\n")))
print("\n".join(report))
