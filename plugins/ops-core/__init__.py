"""ops-core: the ops kit's orchestration plugin. Step 1: shared SOUL rules kept in one place.

Rule files (*.md) come from this plugin's rules/ folder (generic) and ~/agents/rules/ (this machine's own; a local file
with the same name replaces the plugin's). Each starts with front matter naming the profiles it applies to:

    ---
    profiles: *            (fnmatch patterns on profile names, space-separated; "default" is ~/.hermes itself)
    exclude: random        (optional)
    ---
    - the rule text, as SOUL bullets

`hermes ops-rules apply` writes the matching rules, in file-name order, into one managed block at the end of each
SOUL.md (between BEGIN and END), replacing the block when the rules change and removing it when none match.
`hermes ops-rules check` lists SOULs that are out of date (exit 1); `show <profile>` prints a profile's block.
Plugin system prompt sections can't carry these (Hermes caps them at 4,000 characters each, 8,000 in all), so the
rules live in SOUL.md like the rest of each profile's instructions. In the gateway the plugin only checks, once at
start, and logs a warning when a SOUL is out of date.
Selftest:  python3 __init__.py --selftest
"""
from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time

BEGIN = "<!-- ops-rules:begin: managed by the ops-core plugin; edit the rule files and run `hermes ops-rules apply` -->"
END = "<!-- ops-rules:end -->"
HEADING = "## Shared rules"
log = logging.getLogger(__name__)


def _root() -> str:
    return os.environ.get("OPS_RULES_ROOT") or os.path.expanduser("~/.hermes")


def _rule_dirs() -> list[str]:
    local = os.environ.get("OPS_RULES_LOCAL") or os.path.expanduser("~/agents/rules")
    return [os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules"), local]


def parse(text: str) -> tuple[dict, str]:
    meta, body = {}, text
    if text.startswith("---\n") and "\n---\n" in text[4:]:
        head, body = text[4:].split("\n---\n", 1)
        for line in head.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return meta, body.strip()


def load_rules(dirs=None) -> list[tuple[str, dict, str]]:
    files = {}
    for d in dirs or _rule_dirs():
        for f in glob.glob(os.path.join(d, "*.md")):
            files[os.path.basename(f)] = f          # a later dir (local) replaces the plugin's file of that name
    out = []
    for name in sorted(files):
        meta, body = parse(open(files[name], encoding="utf-8").read())
        if body:
            out.append((name, meta, body))
    return out


def applies(meta: dict, profile: str) -> bool:
    inc = (meta.get("profiles") or "*").split()
    exc = (meta.get("exclude") or "").split()
    return any(fnmatch.fnmatch(profile, p) for p in inc) and not any(fnmatch.fnmatch(profile, p) for p in exc)


def souls(root: str) -> list[tuple[str, str]]:
    found = [("default", os.path.join(root, "SOUL.md"))]
    found += [(os.path.basename(os.path.dirname(p)), p) for p in sorted(glob.glob(os.path.join(root, "profiles", "*", "SOUL.md")))]
    return [(n, p) for n, p in found if os.path.exists(p)]


def block_for(profile: str, rules) -> str:
    bodies = [body for _, meta, body in rules if applies(meta, profile)]
    return "\n".join([BEGIN, HEADING, ""] + bodies + [END]) if bodies else ""


def render(soul: str, block: str) -> str:
    start, end = soul.find(BEGIN), soul.find(END)
    if not block and start == -1:
        return soul                                  # nothing to add or remove: leave the file exactly as it is
    if start != -1 and end > start:
        before, after = soul[:start].rstrip("\n"), soul[end + len(END):].lstrip("\n")
    else:
        before, after = soul.rstrip("\n"), ""
    parts = [x for x in (before, block, after.rstrip("\n")) if x]
    return "\n\n".join(parts) + "\n"


def run(action: str, dry: bool = False, root: str | None = None, dirs=None) -> list[str]:
    """apply / check: the SOULs that were (or would be) changed."""
    rules, changed = load_rules(dirs), []
    for profile, path in souls(root or _root()):
        soul = open(path, encoding="utf-8").read()
        new = render(soul, block_for(profile, rules))
        if new == soul:
            continue
        changed.append(profile)
        if action == "apply" and not dry:
            shutil.copy2(path, path + ".bak-ops-rules")
            open(path, "w", encoding="utf-8").write(new)
    return changed


def _cli_setup(p):
    p.add_argument("action", choices=["apply", "check", "show"])
    p.add_argument("profile", nargs="?", help="for show")
    p.add_argument("--dry-run", action="store_true")


def _cli(args) -> int:
    if args.action == "show":
        print(block_for(args.profile or "default", load_rules()) or "(no rules apply)")
        return 0
    changed = run(args.action, args.dry_run)
    verb = "would update" if args.action == "check" or args.dry_run else "updated"
    print(f"{verb} {len(changed)} SOUL(s)" + (": " + ", ".join(changed) if changed else ""))
    return 1 if args.action == "check" and changed else 0


def _check_once():
    try:
        stale = run("check")
        if stale:
            log.warning("ops-rules: %d SOUL(s) out of date with the shared rules (%s); run `hermes ops-rules apply`",
                        len(stale), ", ".join(stale))
    except Exception as e:  # never break the gateway over a rules check
        log.warning("ops-rules: check failed: %s", e)


# ---- step 2: the kit's own tools as `hermes ops <tool> ...` ------------------------------------------------------------
TOOLS = {"doctor": "kanban-doctor", "pending": "pending-human", "issues": "issues", "attention": "attention",
         "board-sync": "board-sync", "feeds": "feeds", "quota": "quota-status"}


def tool_path(name: str) -> str | None:
    for p in (os.path.expanduser(f"~/.local/bin/{name}"), os.path.expanduser(f"~/agents/src/{name}/{name}")):
        if os.path.exists(p):
            return p
    return None


def _ops_setup(p):
    p.add_argument("tool", choices=sorted(TOOLS), help="; ".join(f"{k} = {v}" for k, v in sorted(TOOLS.items())))
    p.add_argument("args", nargs=argparse.REMAINDER)


def _ops(args) -> int:
    path = tool_path(TOOLS[args.tool])
    if not path:
        print(f"{TOOLS[args.tool]} is not installed on this machine")
        return 1
    return subprocess.run([path, *args.args]).returncode


# ---- step 2: the stuck-card doctor reacts within minutes, not on its half-hourly cron ---------------------------------
POKE_EVERY = 300          # seconds between scans from the dispatcher tick
_poke = {"at": 0.0, "ids": None, "busy": threading.Lock()}


def doctor_job_id(jobs_path: str) -> str | None:
    try:
        d = json.load(open(jobs_path, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    jobs = d.get("jobs", d) if isinstance(d, dict) else d
    return next((j.get("id") for j in jobs if j.get("name") == "kanban doctor" and j.get("enabled", True)), None)


def new_stuck(out: str, last) -> tuple[list[str], bool]:
    """The stuck card ids in kanban-doctor's output, and whether a card appeared that wasn't listed last time."""
    ids = sorted({l.split()[0] for l in out.splitlines() if l.startswith("t_")})
    return ids, last is not None and bool(set(ids) - set(last))


def _doctor_poke():
    if not _poke["busy"].acquire(blocking=False):
        return
    try:
        path = tool_path("kanban-doctor")
        if not path:
            return
        out = subprocess.run([path], capture_output=True, text=True, timeout=240).stdout
        ids, fresh = new_stuck(out, _poke["ids"])
        _poke["ids"] = ids
        jid = fresh and doctor_job_id(os.path.join(_root(), "cron", "jobs.json"))
        if jid:   # the job itself decides what to do; its monitor script keeps unchanged output from costing a model call
            log.info("ops-core: new stuck-looking card(s) %s; running the kanban doctor job now", ids)
            subprocess.Popen([os.path.expanduser("~/.local/bin/hermes"), "cron", "run", jid],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log.debug("ops-core: doctor poke failed: %s", e)
    finally:
        _poke["busy"].release()


def on_kanban_dispatch_tick(profile_name=None, dry_run=False, **kw):
    if dry_run or profile_name not in (None, "", "default"):   # one poke per machine: the admin profile's dispatcher
        return
    if time.time() - _poke["at"] >= POKE_EVERY:
        _poke["at"] = time.time()
        threading.Thread(target=_doctor_poke, daemon=True).start()


# ---- step 2: a message that starts with @someone else is for that person (replaces a core adapter patch) --------------
def leads_with_other_mention(text: str, bot_id: str, bot_role_ids) -> bool:
    t = (text or "").lstrip()
    if t.startswith(("@everyone", "@here")):
        return True
    m = re.match(r"<@([!&]?)(\d+)>", t)
    if not m:
        return False
    return m.group(2) not in set(bot_role_ids) if m.group(1) == "&" else m.group(2) != str(bot_id)


def pre_gateway_dispatch(event=None, **kw):
    msg = getattr(event, "raw_message", None)
    guild = getattr(msg, "guild", None)          # None for DMs, slash-command interactions and other platforms
    me = getattr(guild, "me", None)
    if me is None or not isinstance(getattr(msg, "content", None), str):
        return None
    if leads_with_other_mention(msg.content, str(me.id), {str(r.id) for r in getattr(me, "roles", None) or []}):
        return {"action": "skip", "reason": "starts with a mention of someone else"}
    return None


def register(ctx) -> None:
    ctx.register_cli_command("ops-rules", "Shared SOUL rules: apply, check or show", _cli_setup, _cli)
    ctx.register_cli_command("ops", "Run an ops kit tool: " + ", ".join(sorted(TOOLS)), _ops_setup, _ops)
    ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch)
    home = os.path.realpath(os.environ.get("HERMES_HOME") or _root())
    if "gateway" in " ".join(sys.argv) and home == os.path.realpath(_root()):   # from the root gateway only
        threading.Timer(30, _check_once).start()
        ctx.register_hook("on_kanban_dispatch_tick", on_kanban_dispatch_tick)


def _selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root, plug, local = f"{d}/h", f"{d}/plug", f"{d}/local"
        for x in (f"{root}/profiles/team-qa", f"{root}/profiles/random", plug, local):
            os.makedirs(x)
        w = lambda p, t: open(p, "w", encoding="utf-8").write(t)
        w(f"{root}/SOUL.md", "You are the admin.\n")
        w(f"{root}/profiles/team-qa/SOUL.md", "You are QA.\n\n## Tail\n- keep\n")
        w(f"{root}/profiles/random/SOUL.md", "Random.\n\n\n")             # untouched, odd ending and all
        w(f"{plug}/10-all.md", "---\nprofiles: *\nexclude: random\n---\n- Rule A.\n")
        w(f"{plug}/20-team.md", "---\nprofiles: team-*\n---\n- Rule B (generic).\n")
        w(f"{local}/20-team.md", "---\nprofiles: team-*\n---\n- Rule B (local).\n")
        dirs = [plug, local]
        assert run("check", root=root, dirs=dirs) == ["default", "team-qa"]
        assert run("apply", root=root, dirs=dirs) == ["default", "team-qa"]
        qa = open(f"{root}/profiles/team-qa/SOUL.md", encoding="utf-8").read()
        assert qa.startswith("You are QA.\n\n## Tail\n- keep\n\n" + BEGIN) and "Rule B (local)" in qa and "generic" not in qa, qa
        assert "Rule B" not in open(f"{root}/SOUL.md", encoding="utf-8").read()
        assert open(f"{root}/profiles/random/SOUL.md", encoding="utf-8").read() == "Random.\n\n\n"
        assert run("check", root=root, dirs=dirs) == []                       # idempotent
        w(f"{plug}/10-all.md", "---\nprofiles: *\nexclude: random\n---\n- Rule A, edited.\n")
        assert run("apply", root=root, dirs=dirs) == ["default", "team-qa"]
        qa = open(f"{root}/profiles/team-qa/SOUL.md", encoding="utf-8").read()
        assert qa.count(BEGIN) == 1 and "Rule A, edited." in qa and "- Rule A.\n" not in qa
        os.remove(f"{plug}/10-all.md"); os.remove(f"{plug}/20-team.md"); os.remove(f"{local}/20-team.md")
        assert run("apply", root=root, dirs=dirs) == ["default", "team-qa"]   # no rules left: block removed
        assert open(f"{root}/SOUL.md", encoding="utf-8").read() == "You are the admin.\n"
        assert open(f"{root}/profiles/team-qa/SOUL.md", encoding="utf-8").read() == "You are QA.\n\n## Tail\n- keep\n"
        w(f"{d}/jobs.json", json.dumps({"jobs": [{"id": "a1", "name": "issue handler"}, {"id": "b2", "name": "kanban doctor"}]}))
        assert doctor_job_id(f"{d}/jobs.json") == "b2" and doctor_job_id(f"{d}/missing.json") is None
    out = "t_1 blocked kind=- @dev [blocked] x | y\nt_2 ready kind=- @qa [not-picked-up] z | \n"
    assert new_stuck(out, None) == (["t_1", "t_2"], False)          # first scan only learns the set
    assert new_stuck(out, ["t_1", "t_2"]) == (["t_1", "t_2"], False)
    assert new_stuck(out, ["t_1"]) == (["t_1", "t_2"], True)
    assert new_stuck("no stuck-looking cards", ["t_1"]) == ([], False)
    cases = {"<@222> can you check this": True, "  <@!222> hi": True, "<@&999> team, look": True, "@everyone heads up": True,
             "@here quick one": True, "<@111> what's pending?": False, "<@!111> hi": False, "<@&555> do this": False,
             "hey <@222> look": False, "what's pending?": False, "": False}
    for text, want in cases.items():                                   # the same cases as the old adapter patch
        assert leads_with_other_mention(text, "111", {"555"}) == want, text
    from types import SimpleNamespace as N
    me = N(id=111, roles=[N(id=555)])
    ev = lambda content, guild=N(me=me): N(raw_message=N(content=content, guild=guild))
    assert pre_gateway_dispatch(event=ev("<@222> for you"))["action"] == "skip"
    assert pre_gateway_dispatch(event=ev("<@111> for the bot")) is None
    assert pre_gateway_dispatch(event=ev("<@222> in a DM", guild=None)) is None
    assert pre_gateway_dispatch(event=N(raw_message=None)) is None and pre_gateway_dispatch() is None
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    else:
        sys.exit("usage: python3 __init__.py --selftest   (the commands run as `hermes ops-rules ...`)")
