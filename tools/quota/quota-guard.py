#!/usr/bin/env python3
"""Quota governor (Hermes cron "quota guard", every 5 minutes, no LLM).

For every profile it applies quota_lib.run_allowed to the profile's own model chain: scheduled agent
jobs keep running on the first two providers and pause when they would fall to the third; a profile in
auto mode (or every mode, with a machine's all_modes caps) also pauses once the second provider reaches the caps (quota_lib) Kanban
workers of paused profiles stop being dispatched (kanban.dispatch_profiles). Everything it paused is
resumed when the limits allow again (auto-mode jobs only while auto mode is still on); jobs paused by
hand are never touched. Before a pause it posts one wrap-up notice for profiles with scheduled work (quota_lib.wrap_up), and a
provider Hermes recently gave up on in a profile counts as used up there (quota_lib.profile_usage).
Prints only when something changed; Hermes posts that text.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/agents/src/quota"))
import quota_lib as q  # noqa: E402


def hermes(*args):
    return subprocess.run([q.HERMES, *args], capture_output=True, text=True, timeout=180)


def agent_jobs(home):
    try:
        with open(os.path.join(home, "cron", "jobs.json")) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    # Hermes marks a paused job enabled=false, so paused ones count too (else they could never be resumed).
    return [j for j in (data.get("jobs", []) if isinstance(data, dict) else data)
            if (j.get("enabled") or is_paused(j)) and not j.get("no_agent")]


def is_paused(job):
    return bool(job.get("paused_at")) or job.get("state") == "paused"


def set_kanban(allowed_profiles):
    hermes("config", "set", "kanban.dispatch_profiles", json.dumps(sorted(allowed_profiles)))


def main():
    memo = {}

    def getu(provider):
        key = "claude" if q.is_claude(provider) else provider
        if key not in memo:
            memo[key] = q.usage(provider, fresh=True)
        return memo[key]

    state = q.load_gov_state()
    paused, lines = state["paused"], []
    wrapping, now_wrapping = state.get("wrapping", []), []
    blocked = []
    all_names = []
    for name, home in q.profiles():
        all_names.append(name)
        try:
            providers = q.chain(home)
        except Exception:
            continue
        auto = q.auto_mode(home)
        capped = q.caps(home)  # auto mode, or caps the owner made permanent (quota-caps.json)
        pu = q.profile_usage(home, getu)
        cp = q.cap_providers(home) if capped else ()
        ok, why = q.run_allowed(providers, capped, pu, cp, q.paid_ok(home))
        wrap = q.wrap_up(providers, capped, pu, cp, q.paid_ok(home)) if ok else ""
        if not ok:
            blocked.append(name)
        stopped, started, failed = [], [], []
        for job in agent_jobs(home):
            key = f"{name}:{job['id']}"
            if job.get("name") == q.AUTO_JOB and not auto:
                paused.pop(key, None)  # auto mode is off: the automode command owns this job
                continue
            if not ok and not is_paused(job):
                r = hermes("--profile", name, "cron", "pause", job["id"])
                if r.returncode == 0:
                    paused[key] = {"profile": name, "id": job["id"], "name": job.get("name", "")}
                    stopped.append(job.get("name", job["id"]))
                else:
                    failed.append(f"pause {job.get('name', job['id'])}: rc={r.returncode} {(r.stderr or r.stdout).strip()[-300:]}")
            elif ok and key in paused and is_paused(job):
                r = hermes("--profile", name, "cron", "resume", job["id"])
                if r.returncode == 0:
                    paused.pop(key)
                    started.append(job.get("name", job["id"]))
                else:
                    failed.append(f"resume {job.get('name', job['id'])}: rc={r.returncode} {(r.stderr or r.stdout).strip()[-300:]}")
            elif ok and key in paused:
                paused.pop(key)  # someone resumed it already
        tag = f"{name} (auto mode)" if auto else f"{name} (auto-mode caps)" if capped else name
        jobs = agent_jobs(home)
        if wrap and name not in wrapping and any(not is_paused(j) for j in jobs):
            lines.append(f"⏳ {tag}: {wrap}. Scheduled work is wrapping up (runs finish their step and save a handoff) before the pause.")
        if wrap:
            now_wrapping.append(name)
        if stopped:
            lines.append(f"⏸ {tag}: paused {', '.join(stopped)}. {why}. Resumes automatically.")
        if started:
            lines.append(f"▶ {tag}: quota is back, resumed {', '.join(started)}.")
        if failed:  # a failed pause/resume used to be silent, leaving jobs stuck
            lines.append(f"⚠ {tag}: quota governor could not " + "; ".join(failed))
    # The allowlist is only written once something has been blocked; after that it tracks new profiles too.
    allowed = sorted(n for n in all_names if n not in blocked)
    kanban_allowed = state["kanban_allowed"]
    if (blocked or kanban_allowed is not None) and allowed != kanban_allowed:
        set_kanban(allowed)
        kanban_allowed = allowed
    if sorted(blocked) != sorted(state["kanban_blocked"]):
        lines.append(f"⏸ Kanban: no new workers for {', '.join(blocked)} until quota allows." if blocked
                     else "▶ Kanban: dispatching workers again.")
    q.save_gov_state({"paused": paused, "kanban_blocked": sorted(blocked), "kanban_allowed": kanban_allowed,
                      "wrapping": now_wrapping})
    if lines:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
