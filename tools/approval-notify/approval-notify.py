#!/usr/bin/env python3
"""Ping the owner in #assistant about agents waiting for them (Hermes cron "approval notify", every minute,
no LLM). Reads ~/.hermes/approval-queue.jsonl, written by the approval-notify plugin in every profile.
A request is announced once, only if it is still unanswered GRACE seconds after it started, and a Discord
command approval once more when its buttons expire (Hermes caps them at 15 min: approvals.discord_prompt_timeout)
while the request itself stays open for approvals.timeout (3 h, 6 h in auto mode), answerable with /approve or
/deny in the same chat. Kanban tasks blocked on a human are announced once each. Prints nothing when there's
nothing new.
`approval-notify.py --selftest` checks the logic."""
import json
import os
import re
import sys
import time

QUEUE = os.path.expanduser("~/.hermes/approval-queue.jsonl")
STATE = os.path.expanduser("~/.hermes/approval-notify-state.json")
GRACE = 180         # seconds: answered within 3 minutes = no ping (owner, 2026-11-04)
MAX_AGE = 21600     # older unanswered requests have timed out (approvals.timeout: 3 h, 6 h in auto mode)
BUTTONS = 900       # Discord buttons expire after this (approvals.discord_prompt_timeout, Hermes max 900)
KEEP = 86400        # queue lines kept this long
KIND = {"approval": "approve a command", "clarify": "answer a question"}


def owner_id():
    try:
        m = re.search(r"^DISCORD_ALLOWED_USERS=(\d+)", open(os.path.expanduser("~/.hermes/.env")).read(), re.M)
        return m.group(1) if m else None
    except OSError:
        return None


def where(session_key, profile):
    # e.g. agent:project:discord:group:<chat>:<user>  or  agent:main:discord:thread:<thread>:<thread>
    parts = (session_key or "").split(":")
    who = profile if profile and profile != "?" else (parts[1] if len(parts) > 1 else "an agent")
    who = "assistant" if who in ("default", "main") else who
    chat = parts[4] if len(parts) > 4 and parts[2] == "discord" and parts[4].isdigit() else None
    return who, (f"<#{chat}>" if chat else (parts[2] if len(parts) > 2 else "its chat"))


def _clip(text, n):
    """At most n characters, cut at a word boundary with an ellipsis."""
    text = " ".join(str(text or "").split())
    if len(text) <= n:
        return text
    cut = text[:n - 1]
    return (cut.rsplit(" ", 1)[0] if " " in cut[n // 2:] else cut).rstrip(" ,;:.") + "…"


def pending(records, notified, now):
    """New lines to announce, and the ids they cover."""
    resolved = {r["id"] for r in records if r.get("event") == "resolved"}
    lines, ids = [], []
    for r in records:
        rid = r.get("id")
        if not rid:
            continue
        if r.get("event") == "request" and rid not in resolved and GRACE <= now - r["at"] <= MAX_AGE:
            who, chan = where(r.get("session_key"), r.get("profile"))
            what = KIND.get(r.get("kind"), f"respond ({r.get('kind')})")
            prompt = _clip(r.get("prompt"), 300)
            discord = ":discord:" in (r.get("session_key") or "") and r.get("kind") == "approval"
            if not discord or now - r["at"] < BUTTONS:
                if rid not in notified:
                    hint = " (buttons work for 15 min; after that type `/approve` or `/deny` there)" if discord else ""
                    lines.append(f"• **{who}** is waiting for you to {what} in {chan}" + (f": `{prompt}`" if prompt else "") + hint)
                    ids.append(rid)
            elif rid + ":expired" not in notified:
                lines.append(f"• **{who}** is still waiting in {chan}" + (f" (`{_clip(prompt, 160)}`)" if prompt else "") +
                             ": the buttons have expired, but the request stays open. Type `/approve` (or `/approve session`) or `/deny` there.")
                ids += [rid, rid + ":expired"]
        elif r.get("event") == "kanban_blocked" and rid not in notified:
            reason = _clip(r.get("reason"), 700)
            lines.append(f"• Kanban task {r.get('task_id')} ({r.get('assignee') or 'unassigned'}) is blocked on you" + (f": {reason}" if reason else "") + f" (full card: `hermes kanban show {r.get('task_id')}`)")
            ids.append(rid)
    return lines, ids


def main():
    now = time.time()
    try:
        records = [json.loads(line) for line in open(QUEUE) if line.strip()]
    except (OSError, ValueError):
        records = []
    try:
        notified = set(json.load(open(STATE)))
    except (OSError, ValueError):
        notified = set()
    lines, ids = pending(records, notified, now)
    keep = [r for r in records if now - r.get("at", now) <= KEEP]
    live_ids = {r.get("id") for r in keep} | {f"{r.get('id')}:expired" for r in keep}
    with open(STATE, "w") as fh:
        json.dump(sorted((notified | set(ids)) & live_ids | set(ids)), fh)
    if len(keep) != len(records):
        with open(QUEUE + ".tmp", "w") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in keep)
        os.replace(QUEUE + ".tmp", QUEUE)
    if lines:
        uid = owner_id()
        print((f"<@{uid}> " if uid else "") + "waiting for you:\n" + "\n".join(lines))


def selftest():
    now = 10_000.0
    recs = [
        {"event": "request", "id": "a", "kind": "approval", "at": now - 200, "profile": "jobs",
         "session_key": "agent:jobs:discord:group:200000000000000001:100000000000000001", "prompt": "rm -rf build"},
        {"event": "request", "id": "b", "kind": "clarify", "at": now - 10, "profile": "project", "session_key": "x"},
        {"event": "request", "id": "c", "kind": "approval", "at": now - 90, "profile": "tools", "session_key": "y"},
        {"event": "resolved", "id": "c", "at": now - 80},
        {"event": "kanban_blocked", "id": "kanban:t1:1", "task_id": "t1", "assignee": "project-qa", "reason": "needs sign-off", "at": now - 5},
    ]
    lines, ids = pending(recs, set(), now)
    assert ids == ["a", "kanban:t1:1"], ids                       # b is too fresh, c was answered
    assert "<#200000000000000001>" in lines[0] and "approve a command" in lines[0]
    assert pending(recs, {"a", "kanban:t1:1"}, now)[1] == []      # announced once
    assert where("agent:main:discord:thread:9:9", "default")[0] == "assistant"
    assert "/approve" in lines[0]                                 # first ping explains the fallback
    late = now + BUTTONS                                          # a's buttons have expired, still unanswered
    lines2, ids2 = pending(recs, {"a", "kanban:t1:1"}, late)
    assert "a:expired" in ids2 and "buttons have expired" in lines2[0], lines2
    assert "a:expired" not in pending(recs, {"a", "a:expired", "kanban:t1:1", "b"}, late)[1]   # expiry ping once
    assert pending(recs, set(), now + MAX_AGE + 100)[1] == ["kanban:t1:1"]                      # past the wait: no ping
    print("approval-notify selftest ok")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
