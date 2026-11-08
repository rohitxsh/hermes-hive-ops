#!/usr/bin/python3
"""hermes-update-notice (the owner, 2026-10-30): tell the owner in #assistant, once, when a new stable Hermes release is out,
with its changelog, the installed version, a one-line risk estimate for our local patches, and an offer to let the
assistant run the update. No reminders: each release tag is announced at most once (state in
~/agents/hermes-update-notice.json). No LLM; prints nothing when there is nothing new, so Hermes posts nothing.
Usage: hermes-update-notice [--dry-run]"""
import json
import os
import re
import subprocess
import sys
import urllib.request

HOME = os.path.expanduser("~")
STATE = f"{HOME}/agents/hermes-update-notice.json"
API = "https://api.github.com/repos/NousResearch/hermes-agent/releases/latest"  # stable only: no pre-releases
SRC = f"{HOME}/.hermes/hermes-agent"
MAX_NOTES = 3200  # Discord splits long posts; keep it to about two messages


def get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "hermes-update-notice"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def installed():
    # The CLI is slow to start when many cron jobs fire at the same minute (over 60 s seen),
    # so retry once with a longer timeout before failing the run.
    for t in (90, 240):
        try:
            out = subprocess.run([f"{HOME}/.local/bin/hermes", "--version"], capture_output=True, text=True,
                                 timeout=t, stdin=subprocess.DEVNULL).stdout
            break
        except subprocess.TimeoutExpired:
            if t == 240:
                raise
    m = re.search(r"\bv(\d+\.\d+\.\d+)", out)
    assert m, f"can't read the installed version from: {out[:120]!r}"
    return m.group(1)


def newer(a, b):
    return tuple(map(int, a.split("."))) > tuple(map(int, b.split(".")))


def git(*args):
    return subprocess.run(["git", "-C", SRC, *args], capture_output=True, text=True, timeout=300, check=True).stdout


def patched_files():
    """Files our local patches change: everything modified or added in Hermes's git tree."""
    return {line[3:].strip() for line in git("status", "--porcelain").splitlines() if line[3:].strip().endswith(".py")}


def release_changes(have, tag, patched):
    """Which patched files the release touches. Fetches only the new tag; the working tree is not changed."""
    git("fetch", "--quiet", "--no-tags", "origin", f"refs/tags/{tag}:refs/tags/{tag}")
    return set(git("diff", "--name-only", f"v{have}", tag, "--", *sorted(patched)).split())


def risk(patched, changed, notes):
    """One line: low / medium / high, from how many patched files the release touches."""
    hit = sorted(patched & changed)
    breaking = bool(re.search(r"\bbreaking\b", notes, re.I))
    level = "high" if len(hit) > 3 else "medium" if hit or breaking else "low"
    why = (f"the release changes {len(hit)} of the {len(patched)} files our local patches edit"
           + (f" ({', '.join(hit[:4])}{', …' if len(hit) > 4 else ''})" if hit else "")
           + (" and its notes mention breaking changes" if breaking else ""))
    then = {"low": "the patches should re-apply as they are",
            "medium": "expect to re-check those patches after updating",
            "high": "expect some patches to need rework; update when there's time to test"}[level]
    return f"**Risk: {level}.** {why[0].upper() + why[1:]}; {then}."


def main():
    dry = "--dry-run" in sys.argv
    rel = get(API)
    tag = rel["tag_name"]
    latest = tag.lstrip("v")
    have = installed()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    if not newer(latest, have) or state.get("announced") == tag:
        if dry:
            print(f"nothing to post: installed v{have}, latest {tag}, already announced: {state.get('announced')}")
        return
    notes = (rel.get("body") or "").strip()
    try:
        patched = patched_files()
        risk_line = risk(patched, release_changes(have, tag, patched), notes)
    except Exception as e:  # noqa: BLE001 - the notice still goes out, just without the estimate
        risk_line = f"**Risk:** couldn't estimate ({type(e).__name__})."
    if len(notes) > MAX_NOTES:
        notes = notes[:notes.rfind("\n", 0, MAX_NOTES)].rstrip() + "\n…"
    print(f"**Hermes {tag} is out.** Installed here: **v{have}** (latest released {rel.get('published_at', '')[:10]}).\n"
          f"{risk_line}\n\n{notes}\n\nFull notes: <{rel['html_url']}>\n\n"
          f"**Should I update Hermes to {tag} myself?** Reply here with yes (or a time, e.g. \"tonight\") and the assistant "
          "backs up, updates, re-applies and checks every local patch, and restarts only when no work is running. "
          "This is the only notice for this release.")
    if not dry:
        state["announced"] = tag
        tmp = STATE + ".tmp"
        json.dump(state, open(tmp, "w"))
        os.replace(tmp, STATE)


if __name__ == "__main__":
    assert newer("0.23.0", "0.22.5") and not newer("0.22.5", "0.22.5") and newer("0.22.10", "0.22.9")
    assert risk({"a.py"}, {"b.py"}, "").startswith("**Risk: low.**")
    assert risk({"a.py", "b.py"}, {"b.py"}, "").startswith("**Risk: medium.**")
    assert risk(set("abcde"), set("abcde"), "").startswith("**Risk: high.**")
    assert "breaking" in risk({"a.py"}, set(), "BREAKING: x")
    try:
        main()
    except (OSError, TimeoutError) as e:  # GitHub unreachable: stay quiet, the next run checks again
        print(f"hermes-update-notice: GitHub not reachable ({e}); will retry", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 - one line for the issue list, then fail the job
        print(f"hermes-update-notice failed: {type(e).__name__}: {e}")
        sys.exit(1)
