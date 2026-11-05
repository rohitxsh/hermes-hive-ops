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

import fnmatch
import glob
import logging
import os
import shutil
import sys
import threading

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


def register(ctx) -> None:
    ctx.register_cli_command("ops-rules", "Shared SOUL rules: apply, check or show", _cli_setup, _cli)
    home = os.path.realpath(os.environ.get("HERMES_HOME") or _root())
    if "gateway" in " ".join(sys.argv) and home == os.path.realpath(_root()):   # once, from the root gateway only
        threading.Timer(30, _check_once).start()


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
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    else:
        sys.exit("usage: python3 __init__.py --selftest   (the commands run as `hermes ops-rules ...`)")
