#!/usr/bin/python3
"""hermes-update-notice (the owner, 2026-10-30): tell the owner in #assistant, once, when a new stable Hermes release is out,
with its changelog. No reminders: each release tag is announced at most once (state in
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
MAX_NOTES = 3500  # Discord splits long posts; keep it to about two messages


def installed():
    out = subprocess.run([f"{HOME}/.local/bin/hermes", "--version"], capture_output=True, text=True,
                         timeout=60, stdin=subprocess.DEVNULL).stdout
    m = re.search(r"\bv(\d+\.\d+\.\d+)", out)
    assert m, f"can't read the installed version from: {out[:120]!r}"
    return m.group(1)


def newer(a, b):
    return tuple(map(int, a.split("."))) > tuple(map(int, b.split(".")))


def main():
    dry = "--dry-run" in sys.argv
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "hermes-update-notice"})
    rel = json.load(urllib.request.urlopen(req, timeout=30))
    tag = rel["tag_name"]
    latest = tag.lstrip("v")
    have = installed()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    if not newer(latest, have) or state.get("announced") == tag:
        if dry:
            print(f"nothing to post: installed v{have}, latest {tag}, already announced: {state.get('announced')}")
        return
    notes = (rel.get("body") or "").strip()
    if len(notes) > MAX_NOTES:
        notes = notes[:notes.rfind("\n", 0, MAX_NOTES)].rstrip() + "\n…"
    print(f"**Hermes {tag} is out** (installed: v{have}, released {rel.get('published_at', '')[:10]}).\n\n"
          f"{notes}\n\nFull notes: <{rel['html_url']}>\n"
          "This is the only notice for this release.")
    if not dry:
        state["announced"] = tag
        tmp = STATE + ".tmp"
        json.dump(state, open(tmp, "w"))
        os.replace(tmp, STATE)


if __name__ == "__main__":
    assert newer("0.23.0", "0.22.5") and not newer("0.22.5", "0.22.5") and newer("0.22.10", "0.22.9")
    try:
        main()
    except (OSError, TimeoutError) as e:  # GitHub unreachable: stay quiet, the next run checks again
        print(f"hermes-update-notice: GitHub not reachable ({e}); will retry", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 - one line for the issue list, then fail the job
        print(f"hermes-update-notice failed: {type(e).__name__}: {e}")
        sys.exit(1)
