#!/usr/bin/env python3
"""Self-heal for a known Hermes gateway fault (Hermes cron "gateway heal", every 2 minutes, no LLM).

After a Discord reconnect the gateway can lose track of live conversations: every new message there gets
the ✅ tick but no reply, and the logs show "Session … paused: not_found". When that line appears, this
schedules a graceful in-band restart (SIGUSR1: the gateway stops taking new work and lets running turns and
jobs finish first) and posts one note. At most one restart per COOLDOWN; prints nothing otherwise.
`gateway-heal.py --selftest` checks the log parsing.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

H = os.path.expanduser("~/.hermes")
STATE = os.path.join(H, "gateway-heal.json")
COOLDOWN = 900
LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ WARNING gateway\.session_authority: Session (\S+) paused: not_found")


def logs():
    return [os.path.join(H, "logs", "agent.log")] + glob.glob(os.path.join(H, "profiles", "*", "logs", "agent.log"))


def new_faults(lines, since):
    """Session ids that newly hit paused: not_found after `since` (a 'YYYY-MM-DD HH:MM:SS' string)."""
    found = set()
    for line in lines:
        m = LINE.match(line)
        if m and m.group(1) > since:
            found.add(m.group(2))
    return found


def gateway_started():
    out = subprocess.run(["systemctl", "show", "-p", "ActiveEnterTimestamp", "--value", "agent-worker@hermes"],
                         capture_output=True, text=True).stdout.strip()
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.strptime(" ".join(out.split()[1:3]), "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return "0"


def main():
    try:
        state = json.load(open(STATE))
    except (OSError, ValueError):
        state = {}
    since = max(state.get("checked", "0"), gateway_started())  # faults before the last start are already healed
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    faults = set()
    for f in logs():
        try:
            with open(f, errors="replace") as fh:
                fh.seek(max(0, os.path.getsize(f) - 2_000_000))
                faults |= new_faults(fh.readlines(), since)
        except OSError:
            pass
    state["checked"] = now_str
    if faults and time.time() - state.get("restarted_at", 0) > COOLDOWN:
        # Delay so this run finishes and its note is delivered before the gateway starts draining.
        subprocess.run(["sudo", "-n", "systemd-run", "--on-active=30", "systemctl", "kill", "-s", "SIGUSR1",
                        "--kill-whom=main", "agent-worker@hermes"], capture_output=True)
        state["restarted_at"] = time.time()
        print(f"♻ The gateway lost track of {len(faults)} conversation(s) after a Discord reconnect "
              f"(messages got a ✅ but no reply). Restarting it gracefully now; running work finishes first. "
              f"If something you sent in the last few minutes got no answer, please send it again.")
    with open(STATE, "w") as fh:
        json.dump(state, fh)


def selftest():
    lines = ["2026-10-25 00:53:59,675 WARNING gateway.session_authority: Session 20261022_091631_62b62465 paused: not_found",
             "2026-10-25 01:09:35,271 WARNING gateway.session_authority: Session 20261022_224728_8ea5b87c paused: not_found",
             "2026-10-25 01:10:00,000 INFO gateway.run: something else"]
    assert new_faults(lines, "2026-10-25 00:00:00") == {"20261022_091631_62b62465", "20261022_224728_8ea5b87c"}
    assert new_faults(lines, "2026-10-25 01:00:00") == {"20261022_224728_8ea5b87c"}
    assert new_faults(lines, "2026-10-25 02:00:00") == set()
    print("gateway-heal selftest ok")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
