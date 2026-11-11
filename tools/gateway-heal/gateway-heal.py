#!/usr/bin/env python3
"""Self-heal for a known Hermes gateway fault (Hermes cron "gateway heal", every 2 minutes, no LLM).

After a Discord reconnect the gateway can lose track of live conversations: every new message there gets
the ✅ tick but no reply, and the logs show "Session … paused: not_found". When that line appears, this
schedules a graceful in-band restart (SIGUSR1: the gateway stops taking new work and lets running turns and
jobs finish first) and posts one note. At most one restart per COOLDOWN; prints nothing otherwise.
`gateway-heal.py --selftest` checks the log parsing and the cooldown state (a fault seen during the cooldown stays
pending until a restart is actually scheduled).
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


def restart():
    """Graceful restart in 30 s (so this run's note is delivered before the gateway drains); True if it was scheduled."""
    r = subprocess.run(["sudo", "-n", "systemd-run", "--on-active=30", "systemctl", "kill", "-s", "SIGUSR1",
                        "--kill-whom=main", "agent-worker@hermes"], capture_output=True, text=True)
    return r.returncode == 0


def step(state, faults, now, now_str, do_restart):
    """Update state for one run; returns the note to post, if any. Faults found during the cooldown, or when the
    restart couldn't be scheduled, stay pending: `checked` only moves past them once a restart was scheduled."""
    if not faults:
        state["checked"] = now_str
        return None
    if now - state.get("restarted_at", 0) <= COOLDOWN:
        return None
    if not do_restart():
        if now - state.get("failed_note_at", 0) > COOLDOWN:   # one note per cooldown, not every 2 minutes
            state["failed_note_at"] = now
            return (f"⚠ The gateway lost track of {len(faults)} conversation(s), but scheduling its graceful restart "
                    f"failed (sudo systemd-run). Restart it when idle: sudo systemd-run --unit hermes-restart-idle-$(date +%s) "
                    f"--collect ~/.local/bin/hermes-restart-idle")
        return None
    state["checked"] = now_str
    state["restarted_at"] = now
    return (f"♻ The gateway lost track of {len(faults)} conversation(s) after a Discord reconnect "
            f"(messages got a ✅ but no reply). Restarting it gracefully now; running work finishes first. "
            f"If something you sent in the last few minutes got no answer, please send it again.")


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
    msg = step(state, faults, time.time(), now_str, restart)
    if msg:
        print(msg)
    with open(STATE, "w") as fh:
        json.dump(state, fh)


def selftest():
    lines = ["2026-10-25 00:53:59,675 WARNING gateway.session_authority: Session 20261022_091631_62b62465 paused: not_found",
             "2026-10-25 01:09:35,271 WARNING gateway.session_authority: Session 20261022_224728_8ea5b87c paused: not_found",
             "2026-10-25 01:10:00,000 INFO gateway.run: something else"]
    assert new_faults(lines, "2026-10-25 00:00:00") == {"20261022_091631_62b62465", "20261022_224728_8ea5b87c"}
    assert new_faults(lines, "2026-10-25 01:00:00") == {"20261022_224728_8ea5b87c"}
    assert new_faults(lines, "2026-10-25 02:00:00") == set()
    # a fault seen during the cooldown stays pending and is healed once the cooldown ends (review finding)
    st, calls = {"checked": "2026-11-12 04:00:00", "restarted_at": 1000.0}, []
    ok = lambda: calls.append(1) or True
    assert step(st, {"s1"}, 1000.0 + 60, "2026-11-12 04:06:00", ok) is None and st["checked"] == "2026-11-12 04:00:00"
    assert step(st, {"s1"}, 1000.0 + COOLDOWN + 60, "2026-11-12 04:16:00", ok).startswith("♻") and calls == [1]
    assert st["checked"] == "2026-11-12 04:16:00" and st["restarted_at"] == 1000.0 + COOLDOWN + 60
    # a restart that can't be scheduled keeps the fault pending and notes it once per cooldown
    st, bad = {"checked": "2026-11-12 04:00:00"}, (lambda: False)
    assert step(st, {"s2"}, 5000.0, "2026-11-12 05:00:00", bad).startswith("⚠") and st["checked"] == "2026-11-12 04:00:00"
    assert step(st, {"s2"}, 5120.0, "2026-11-12 05:02:00", bad) is None and "restarted_at" not in st
    assert step(st, {"s2"}, 5240.0, "2026-11-12 05:04:00", ok).startswith("♻") and st["checked"] == "2026-11-12 05:04:00"
    print("gateway-heal selftest ok")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
