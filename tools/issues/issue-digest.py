#!/usr/bin/env python3
"""Issue digest (Hermes cron "issue digest", every 10 minutes, no LLM).

Puts every profile's problems in one place for the assistant:
- new WARNING / ERROR / CRITICAL lines of each profile's logs/errors.log,
- scheduled jobs whose last run failed,
- the VM self-check (run at most once an hour),
- issues agents report themselves with `report-issue "..."`.
Similar messages are grouped (numbers and ids replaced) and written to ~/agents/issues/open.md, newest
first. New errors, failed jobs, self-check problems and reported issues are printed, and Hermes posts that
text to the assistant's channel; warnings only go to the file. Messages matching a pattern in
~/agents/issues/known.txt (one regex per line, # comments) stay in the file, marked known, but never post.

Issues close by themselves: a log error or warning after QUIET seconds without recurring, a failed job once
its next run succeeds (or it's removed), a self-check problem once the hourly check no longer reports it.
Anything can be closed by hand: `issues resolve <id> "what fixed it"` (`issues` lists open ones). A closed
issue that comes back reopens and alerts again. Closed issues stay listed for KEEP_DAYS.

The assistant's "issue handler" job works the alerts: `issues pending` lists the ones it hasn't handled since they
(re)opened (stable text, so the job's monitor only wakes it for new ones), `issues show <id>` prints one in full, and
`issues handled <id> fixed|transient|asked|blocked "note"` records the outcome (fixed and transient also resolve it).
Handled outcomes live in assistant-handled.json, a file this digest never writes, so the two can't overwrite each other.
"""
import datetime
import glob
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
HERMES_DIR = os.path.join(HOME, ".hermes")
DIR = os.path.join(HOME, "agents", "issues")
STATE, KNOWN, REPORTED, OPEN = (os.path.join(DIR, n) for n in ("state.json", "known.txt", "reported.jsonl", "open.md"))
HANDLED = os.path.join(DIR, "assistant-handled.json")
OUTCOMES = ("fixed", "transient", "asked", "blocked")
KEEP_DAYS = 7
QUIET = 24 * 3600          # a log issue not seen this long counts as fixed
REPOST_AFTER = 24 * 3600   # an open issue quiet this long is posted again when it comes back
HEALTH_EVERY = 3600
MAX_READ = 2_000_000       # bytes read per file per run (also how far back the first run looks)
MAX_POST = 8
ESCALATE_AFTER = 30 * 60  # the issue handler (every 10 min) gets this long to fix or close a new alert before it's posted
# known-add refuses a pattern that would also hide one of these (real failures must always surface)
CANARIES = ("cron: Job 'x' failed: RuntimeError: boom", "self-check: disk / is 95% full",
            "report-issue: search is broken", "agent.conversation_loop: API call failed after 3 retries. HTTP 500",
            "gateway.run: Fatal discord adapter error (x)", "agent.tool_executor: Tool terminal returned error")
LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ (WARNING|ERROR|CRITICAL) (?:\[[^\]]*\] )?(\S+): (.*)")
ALERT = ("ERROR", "CRITICAL", "JOB", "CHECK", "REPORTED")
# Errors that are just a provider limit being hit (owner, 2026-10-26: not issues). Claude reports its usage limit as a
# rate limit. Only log lines and failed-job errors are filtered; agents' own reports and the self-check never are.
QUOTA = re.compile(r"\b(429|402)\b|rate.?limit|RateLimitError|usage.?limit|insufficient_quota|quota (exceeded|exhausted|reached)|"
                   r"out of capacity|free-models-per-day|requires? (more )?credits|payment error|session limit|weekly limit|"
                   r"limit reached|limit has been reached|requires available credits|insufficient_credits|balance is too low|"
                   r"refused for billing|credential pool is exhausted|every entry in cooldown", re.I)


def profiles():
    yield "default", HERMES_DIR
    for home in sorted(glob.glob(os.path.join(HERMES_DIR, "profiles", "*"))):
        if os.path.isfile(os.path.join(home, "config.yaml")):
            yield os.path.basename(home), home


def normalize(msg):
    m = re.sub(r"^(Tool \S+ returned error).*", r"\1", msg)  # agents handle their own tool errors: one group per tool
    m = re.sub(r"/home/[^/\s]+", "~", m)
    m = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27}|\b[0-9a-f]*\d[0-9a-f]*[a-f][0-9a-f]*\b|\b[0-9a-f]*[a-f][0-9a-f]*\d[0-9a-f]*\b", "#", m)
    return re.sub(r"\d+(\.\d+)?", "N", m)[:200]


def issue_id(key):
    return hashlib.sha1(key.encode()).hexdigest()[:6]


def read_new(path, offsets):
    """Lines appended since the last run (whole lines only)."""
    try:
        st = os.stat(path)
    except OSError:
        return []
    ino, pos = offsets.get(path, (st.st_ino, 0))
    if ino != st.st_ino or pos > st.st_size:
        pos = 0  # shortcut: lines written just before a rotation are missed; fine for a digest
    pos = max(pos, st.st_size - MAX_READ)
    with open(path, "rb") as fh:
        fh.seek(pos)
        data = fh.read()
    cut = data.rfind(b"\n") + 1
    offsets[path] = (st.st_ino, pos + cut)
    return data[:cut].decode("utf-8", "replace").splitlines()


def health_script():
    found = glob.glob(os.path.join(HERMES_DIR, "scripts", "agent*-health.sh")) + \
        glob.glob(os.path.join(HERMES_DIR, "profiles", "*", "scripts", "agent*-health.sh"))
    return found[0] if found else None


def load_jobs():
    """{(profile, job id): job} for every profile's cron jobs."""
    jobs = {}
    for name, home in profiles():
        try:
            with open(os.path.join(home, "cron", "jobs.json")) as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        for job in data.get("jobs", []) if isinstance(data, dict) else data:
            jobs[(name, job.get("id"))] = job
    return jobs


def collect(state, now, jobs):
    """Yield (key, level, source, profile, message, when) for everything seen since the last run."""
    offsets = state.setdefault("offsets", {})
    cutoff = now - KEEP_DAYS * 86400
    for name, home in profiles():
        for line in read_new(os.path.join(home, "logs", "errors.log"), offsets):
            m = LINE.match(line)
            if not m:
                continue
            when = time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
            if when >= cutoff and not QUOTA.search(m.group(4)):
                level, source, msg = m.group(2), m.group(3), m.group(4)
                yield f"{level}|{source}|{normalize(msg)}", level, source, name, msg, when
    for (name, job_id), job in jobs.items():
        if job.get("last_status") == "error" and job.get("last_run_at"):
            run = job["last_run_at"]
            if state.setdefault("job_runs", {}).get(f"{name}:{job_id}") == run:
                continue  # this failed run is already counted
            state["job_runs"][f"{name}:{job_id}"] = run
            if QUOTA.search(str(job.get("last_error") or "")):
                continue  # the job died on a provider limit: the quota governor handles that, not an issue
            msg = f"scheduled job '{job.get('name', job_id)}' ({job_id}) failed: {str(job.get('last_error') or '')[:300]}"
            yield f"JOB|{name}|{job_id}|{normalize(str(job.get('last_error') or ''))}", "JOB", "cron", name, msg, now
    for line in read_new(REPORTED, offsets):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        yield f"REPORTED|{r.get('profile')}|{normalize(r.get('text', ''))}", "REPORTED", "report-issue", r.get("profile", "?"), r.get("text", ""), now
    script = health_script()
    if script and now - state.get("health_at", 0) >= HEALTH_EVERY:
        state["health_at"] = now
        try:
            out = subprocess.run(["bash", script], capture_output=True, text=True, timeout=300).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            out = f"- self-check could not run: {exc}"
        state["health_keys"] = []
        for line in out.splitlines():
            if line.startswith("- "):
                msg = line[2:].strip()
                prof = msg.split(":", 1)[0] if re.match(r"^[\w.-]+: ", msg) else "vm"
                state["health_keys"].append(f"CHECK|{normalize(msg)}")
                yield f"CHECK|{normalize(msg)}", "CHECK", "self-check", prof, msg, now


def known_patterns():
    try:
        lines = open(KNOWN).read().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            try:
                out.append(re.compile(line))
            except re.error:
                pass
    return out


def auto_resolve(issues, state, now, jobs):
    """Close open issues whose cause is gone."""
    health_ran = state.get("health_at") == now
    for key, r in issues.items():
        if r.get("resolved_at"):
            continue
        why = None
        if r["level"] == "JOB":
            _, prof, job_id = key.split("|")[:3]
            job = jobs.get((prof, job_id))
            if job is None:
                why = "job removed"
            elif job.get("last_status") == "ok":
                why = "job's next run succeeded"
            elif job.get("paused_at") or job.get("state") == "paused" or not job.get("enabled", True):
                why = "job paused"
        elif r["level"] == "CHECK":
            if health_ran and key not in state.get("health_keys", []):
                why = "self-check passes"
        elif r["level"] != "REPORTED" and now - r["last"] > QUIET:
            why = f"not seen for {QUIET // 3600} h"
        if why:
            r.update(resolved_at=now, resolved_how=why)


def update(state, items, known, now, first_run, jobs=None):
    """Merge new items into state['issues'], close fixed ones; return the lines to post."""
    issues = state.setdefault("issues", {})
    candidates = []
    for key, level, source, profile, msg, when in items:
        rec = issues.get(key)
        reopened = bool(rec and rec.get("resolved_at") and when > rec["resolved_at"])
        if (rec is None or reopened or when - rec["last"] > REPOST_AFTER) and level in ALERT and not first_run:
            candidates.append(key)
        if rec is None:
            rec = issues[key] = {"level": level, "source": source, "profiles": [], "count": 0, "first": when}
        if reopened:
            rec.pop("resolved_at", None)
            rec.pop("resolved_how", None)
            rec["reopened"] = rec.get("reopened", 0) + 1
        rec.update(last=max(when, rec.get("last", when)), sample=msg[:500], id=issue_id(key))
        rec["count"] += 1
        if profile not in rec["profiles"]:
            rec["profiles"].append(profile)
    auto_resolve(issues, state, now, jobs or {})
    for key in [k for k, r in issues.items() if max(r["last"], r.get("resolved_at", 0)) < now - KEEP_DAYS * 86400]:
        del issues[key]
    for k, r in issues.items():  # re-checked every run, so edits to known.txt apply to old issues too
        r["known"] = any(p.search(f"{r['source']}: {r['sample']}") for p in known)
        r.setdefault("id", issue_id(k))
    post = [issues[k] for k in dict.fromkeys(candidates) if k in issues and not issues[k]["known"] and not issues[k].get("resolved_at")]
    for r in post:  # new or back again: the handler gets ESCALATE_AFTER before escalate() posts it
        r["alert_at"] = now
        r.pop("escalated", None)
    return [f"- `{r['id']}` {', '.join(r['profiles'])} · {r['level']}{' (back again)' if r.get('reopened') else ''} "
            f"{r['source']}: {r['sample'][:220]}" for r in post]


def escalate(state, handled, now):
    """Lines for alerts still open, unknown and unhandled ESCALATE_AFTER after they (re)opened; each is decided once."""
    out = []
    for r in state.get("issues", {}).values():
        if not r.get("alert_at") or r.get("escalated") or now - r["alert_at"] < ESCALATE_AFTER:
            continue
        r["escalated"] = now
        h = handled.get(r.get("id"))
        if r.get("resolved_at") or r.get("known") or (h and h.get("reopened", 0) >= r.get("reopened", 0)):
            continue  # closed, known, or the handler dealt with it (it tells the owner itself when they're needed)
        out.append(f"- `{r['id']}` {', '.join(r['profiles'])} · {r['level']}{' (back again)' if r.get('reopened') else ''} "
                   f"{r['source']}: {r['sample'][:220]}")
    return out


def known_add(r, pattern, why, paths):
    """Validate and append a known.txt pattern that retires this issue's message class; returns an error or ''."""
    if r["level"] in ("JOB", "CHECK", "REPORTED"):
        return "failed jobs, self-check problems and agent reports can't be made known; fix or resolve them instead"
    if not pattern.startswith("^" + re.escape(r["source"]) + ": "):
        return f"anchor the pattern to the source: start it with ^{re.escape(r['source'])}: "
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"bad regex: {e}"
    if not rx.search(f"{r['source']}: {r['sample']}"):
        return "the pattern doesn't match this issue's message"
    hit = [c for c in CANARIES if rx.search(c)]
    if hit or len(pattern) < len(r["source"]) + 12:
        return f"too broad (would hide: {hit[0] if hit else 'most messages from this source'})"
    line = f"# {why} (issue handler, {datetime.date.today()}, issue {r['id']})\n{pattern}\n"
    for p in paths:
        if os.path.exists(p) or p == paths[0]:  # the live list always; the template only where it exists
            old = open(p).read() if os.path.exists(p) else ""
            if pattern not in old.splitlines():
                write_atomic(p, old.rstrip("\n") + "\n" + line)
    return ""


def load_handled():
    try:
        with open(HANDLED) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def pending(state, handled):
    """Open alert-level issues the assistant hasn't handled since they last (re)opened; stable text for the monitor."""
    out = []
    for key, r in sorted(state.get("issues", {}).items(), key=lambda kv: kv[1].get("id", "")):
        if r.get("resolved_at") or r.get("known") or r["level"] not in ALERT:
            continue
        h = handled.get(r.get("id"))
        if h and h.get("reopened", 0) >= r.get("reopened", 0):
            continue
        out.append(f"{r.get('id')} | {r['level']} | {', '.join(sorted(r['profiles']))} | {key.split('|', 1)[-1][:300]}")
    return out


def stamp(t):
    return datetime.datetime.fromtimestamp(t).strftime("%m-%d %H:%M")


def render(state, now):
    issues = sorted(state.get("issues", {}).values(), key=lambda r: -r["last"])
    open_ = [r for r in issues if not r.get("resolved_at") and not r.get("known")]
    handled = load_handled()
    groups = [("Needs attention (errors, failed jobs, self-check, reported by agents)", [r for r in open_ if r["level"] in ALERT]),
              ("Warnings", [r for r in open_ if r["level"] not in ALERT]),
              (f"Resolved (last {KEEP_DAYS} days)", sorted([r for r in issues if r.get("resolved_at") and not r.get("known")],
                                                           key=lambda r: -r["resolved_at"])),
              ("Known (matched known.txt, never posted)", [r for r in issues if r.get("known")])]
    out = [f"# Issues on {socket.gethostname()}", "",
           f"Updated {datetime.datetime.fromtimestamp(now):%Y-%m-%d %H:%M} by the \"issue digest\" job (every 10 minutes). "
           f"Every profile's warnings and errors from the last {KEEP_DAYS} days, newest first; similar messages are grouped "
           f"and the message shown is the latest one. Issues close by themselves (log issues after {QUIET // 3600} h "
           "without recurring, failed jobs when the next run succeeds, self-check problems when the check passes); close "
           "one by hand with `issues resolve <id> \"what fixed it\"`. A closed issue that comes back reopens. For harmless "
           "messages, add a regex with a `#` comment above it to ~/agents/issues/known.txt (matched against `source: message`)."]
    for title, rows in groups:
        out += ["", f"## {title} ({len(rows)})", ""]
        if not rows:
            out.append("None.")
            continue
        resolved = title.startswith("Resolved")
        out += ["| Id | Last seen | First seen | Count | Profiles | Level | Source | " + ("Resolved | " if resolved else "") + "Latest message |",
                "|---|---|---|---|---|---|---|" + ("---|" if resolved else "") + "---|"]
        for r in rows:
            h = handled.get(r.get("id")) if not resolved else None
            note = f"[assistant: {h['outcome']}] " if h and h.get("reopened", 0) >= r.get("reopened", 0) else ""
            msg = note + r["sample"].replace("|", "\\|").replace("\n", " ")[:300]
            how = f"{stamp(r['resolved_at'])}: {r.get('resolved_how', '')} | ".replace("\n", " ") if resolved else ""
            out.append(f"| {r.get('id', '')} | {stamp(r['last'])} | {stamp(r['first'])} | {r['count']} | {', '.join(r['profiles'])} | "
                       f"{r['level']} | {r['source']} | {how}{msg} |")
    return "\n".join(out) + "\n"


def write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)


def load_state():
    try:
        with open(STATE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def main():
    os.makedirs(DIR, exist_ok=True)
    now = time.time()
    state = load_state()
    first_run = not state
    jobs = load_jobs()
    update(state, list(collect(state, now, jobs)), known_patterns(), now, first_run, jobs)  # marks new alerts
    lines = escalate(state, load_handled(), now)
    write_atomic(STATE, json.dumps(state))
    write_atomic(OPEN, render(state, now))
    if lines:
        more = f"\n…and {len(lines) - MAX_POST} more." if len(lines) > MAX_POST else ""
        print(f"🔎 Issues the issue handler couldn't close within {ESCALATE_AFTER // 60} minutes (full list: "
              "~/agents/issues/open.md; close one with `issues resolve <id> \"note\"`)\n" + "\n".join(lines[:MAX_POST]) + more)


def cli(args):
    """issues [list] | issues resolve <id> [note] | issues reopen <id> | issues pending | issues show <id>
issues handled <id> fixed|transient|asked|blocked <note>
issues known-add <id> '<regex anchored as ^source: ...>' <why>"""
    state = load_state()
    issues = state.get("issues", {})
    if args[:1] == ["pending"]:
        lines = pending(state, load_handled())
        if lines:
            print("\n".join(lines))
        return
    if args[:1] == ["known-add"] and len(args) >= 4:
        match = [r for r in issues.values() if r.get("id") == args[1]]
        if not match:
            sys.exit(f"no issue with id {args[1]} (see `issues list`)")
        err = known_add(match[0], args[2], " ".join(args[3:]),
                        (KNOWN, os.path.join(HOME, "agents", "src", "issues", "known.txt")))
        if err:
            sys.exit("known-add refused: " + err)
        match[0].update(known=True, resolved_at=time.time(), resolved_how="known-add: " + " ".join(args[3:]))
        write_atomic(STATE, json.dumps(state))
        write_atomic(OPEN, render(state, time.time()))
        print(f"known {match[0]['id']}: added to known.txt and closed")
        return
    if args[:1] in (["show"], ["handled"]) and len(args) >= 2:
        match = [r for r in issues.values() if r.get("id") == args[1]]
        if not match:
            sys.exit(f"no issue with id {args[1]} (see `issues list`)")
        r = match[0]
        handled = load_handled()
        if args[0] == "show":
            print(json.dumps({**r, "first": stamp(r["first"]), "last": stamp(r["last"]),
                              "assistant": handled.get(r["id"])}, indent=1, default=str))
            return
        if len(args) < 3 or args[2] not in OUTCOMES:
            sys.exit("issues handled <id> " + "|".join(OUTCOMES) + ' "note"')
        handled[r["id"]] = {"outcome": args[2], "note": " ".join(args[3:]), "at": stamp(time.time()),
                            "reopened": r.get("reopened", 0)}
        write_atomic(HANDLED, json.dumps(handled, indent=1))
        if args[2] in ("fixed", "transient"):
            r.update(resolved_at=time.time(), resolved_how=f"assistant ({args[2]}): " + (" ".join(args[3:]) or args[2]))
            write_atomic(STATE, json.dumps(state))
        write_atomic(OPEN, render(state, time.time()))
        print(f"handled {r['id']} ({args[2]}): {r['sample'][:120]}")
        return
    if not args or args[0] == "list":
        rows = sorted((r for r in issues.values() if not r.get("resolved_at") and not r.get("known")), key=lambda r: -r["last"])
        for r in rows:
            print(f"{r.get('id')}  {stamp(r['last'])}  {r['level']:8} {', '.join(r['profiles'])}: {r['sample'][:150]}")
        print(f"{len(rows)} open issue(s); full list in {OPEN}")
        return
    if args[0] in ("resolve", "reopen") and len(args) >= 2:
        match = [r for r in issues.values() if r.get("id") == args[1]]
        if not match:
            sys.exit(f"no issue with id {args[1]} (see `issues list`)")
        r = match[0]
        if args[0] == "resolve":
            r.update(resolved_at=time.time(), resolved_how="by hand: " + (" ".join(args[2:]) or "fixed"))
        else:
            r.pop("resolved_at", None)
            r.pop("resolved_how", None)
        write_atomic(STATE, json.dumps(state))
        write_atomic(OPEN, render(state, time.time()))
        print(f"{args[0]}d {r['id']}: {r['sample'][:120]}")
        return
    sys.exit(cli.__doc__)


def selftest():
    assert normalize("Session 3fa9c1d2e4 paused after 12.5s") == "Session # paused after Ns"
    assert normalize("profile jobs failed") == "profile jobs failed"
    assert normalize('Tool terminal returned error (3s): {"output": "x"}') == "Tool terminal returned error"
    m = LINE.match("2026-10-25 01:32:20,123 ERROR [local-ab12cd34] agent.chat: Streaming failed: status 502")
    assert m and m.group(2) == "ERROR" and m.group(3) == "agent.chat", m
    for q in ("API call failed after 3 retries. HTTP 429: Rate limit exceeded: free-models-per-day | provider=openrouter",
              "error_type=ClaudeAPIError: This request would exceed your account's rate limit",
              "HTTP 429: The usage limit has been reached | provider=openai-codex", "Model 'x' requires more credits (402)",
              "HTTP 404: Model 'deepseek/x' requires available credits. Your account balance is too low",
              "Fallback skip: nous/x credential pool is exhausted (every entry in cooldown)"):
        assert QUOTA.search(q), q
    for q in ("quota-status --gate failed: No module named 'yaml'", "Discord Gateway WebSocket transport closed"):
        assert not QUOTA.search(q), q
    known = [re.compile(r"plugins: Failed to parse")]
    now = 1_800_000_000.0
    s = {}
    item = ("ERROR|x|boom", "ERROR", "x", "jobs", "boom 1", now)
    assert update(s, [item], known, now, True) == []                       # first run seeds silently
    assert update(s, [item], known, now, False) == []                      # already known issue: not reposted
    assert update(s, [item[:5] + (now + REPOST_AFTER + 1,)], known, now + REPOST_AFTER + 1, False)   # back after a quiet day
    warn = ("WARNING|y|w", "WARNING", "y", "tools", "w", now)
    assert update(s, [warn], known, now, False) == []                      # warnings only go to the file
    k = ("ERROR|hermes_cli.plugins|p", "ERROR", "hermes_cli.plugins", "project", "Failed to parse plugin.json", now)
    assert update(s, [k], known, now, False) == [] and s["issues"]["ERROR|hermes_cli.plugins|p"]["known"]
    assert "| jobs | ERROR | x |" in render(s, now)
    # auto-resolve: a quiet log error closes, a failed job closes once it runs ok, a self-check item once the check passes
    later = now + REPOST_AFTER + QUIET + 10
    update(s, [], known, later, False)
    assert s["issues"]["ERROR|x|boom"]["resolved_at"] == later and "Resolved" in render(s, later)
    back = update(s, [item[:5] + (later + 5,)], known, later + 5, False)  # it comes back: reopened and posted
    assert back and "back again" in back[0] and not s["issues"]["ERROR|x|boom"].get("resolved_at")
    job = ("JOB|jobs|j1|boom", "JOB", "cron", "jobs", "scheduled job 'apply' failed", now)
    update(s, [job], known, now, False, {("jobs", "j1"): {"last_status": "error"}})
    assert not s["issues"]["JOB|jobs|j1|boom"].get("resolved_at")
    update(s, [], known, now + 60, False, {("jobs", "j1"): {"last_status": "ok"}})
    assert s["issues"]["JOB|jobs|j1|boom"]["resolved_how"] == "job's next run succeeded"
    chk = ("CHECK|disk", "CHECK", "self-check", "vm", "disk / is 90% full", now)
    s["health_at"], s["health_keys"] = now, ["CHECK|disk"]
    update(s, [chk], known, now, False)
    s["health_at"], s["health_keys"] = now + 3600, []
    update(s, [], known, now + 3600, False)
    assert s["issues"]["CHECK|disk"]["resolved_how"] == "self-check passes"
    rep = ("REPORTED|tools|x", "REPORTED", "report-issue", "tools", "search broken", now)
    update(s, [rep], known, now, False)
    update(s, [], known, now + 3 * 86400, False)
    assert not s["issues"]["REPORTED|tools|x"].get("resolved_at")      # reported issues close only by hand
    # pending: open alerts the assistant hasn't handled since they (re)opened; warnings and known ones never
    rid = s["issues"]["REPORTED|tools|x"]["id"]
    assert any(line.startswith(rid + " | REPORTED | tools | ") for line in pending(s, {}))
    assert not any(line.startswith(rid) for line in pending(s, {rid: {"outcome": "asked", "reopened": 0}}))
    assert not any("| WARNING |" in line or "plugins" in line for line in pending(s, {}))
    s["issues"]["REPORTED|tools|x"]["reopened"] = 1                      # came back after being handled
    assert any(line.startswith(rid) for line in pending(s, {rid: {"outcome": "asked", "reopened": 0}}))
    # escalation: a new alert waits ESCALATE_AFTER; handled or closed ones are never posted, unhandled ones once
    e = {}
    new = ("ERROR|z|bang", "ERROR", "z", "team", "bang", now)
    assert update(e, [new], known, now, False) and escalate(e, {}, now + 60) == []
    assert escalate(e, {}, now + ESCALATE_AFTER + 1) and escalate(e, {}, now + ESCALATE_AFTER + 600) == []
    f = {}
    update(f, [new], known, now, False)
    fid = f["issues"]["ERROR|z|bang"]["id"]
    assert escalate(f, {fid: {"outcome": "transient", "reopened": 0}}, now + ESCALATE_AFTER + 1) == []
    # known-add: anchored, matches, not a job/check/report, not broad
    r = {"level": "ERROR", "source": "tools.checkpoint_manager", "id": "abc123",
         "sample": "Git command skipped: git add -A (working directory not found: /x)"}
    tmp = os.path.join("/tmp", f"known-selftest-{os.getpid()}.txt")
    try:
        assert known_add(r, r"^tools\.checkpoint_manager: Git command skipped: git add -A \(working directory not found: ",
                         "harmless", (tmp,)) == "" and "abc123" in open(tmp).read()
        assert "anchor" in known_add(r, r"Git command skipped", "x", (tmp,))
        assert "broad" in known_add(r, r"^tools\.checkpoint_manager: .*", "x", (tmp,))
        assert "doesn't match" in known_add(r, r"^tools\.checkpoint_manager: something else entirely", "x", (tmp,))
        assert "can't" in known_add({**r, "level": "JOB"}, r"^tools\.checkpoint_manager: Git command skipped", "x", (tmp,))
        assert "broad" in known_add({**r, "source": "agent.tool_executor", "sample": "Tool terminal returned error (1s)"},
                                    r"^agent\.tool_executor: Tool terminal returned", "x", (tmp,))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print("issue-digest selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    elif os.path.basename(sys.argv[0]) == "issues" or sys.argv[1:2] in (["list"], ["resolve"], ["reopen"], ["pending"],
                                                                          ["show"], ["handled"], ["known-add"]):
        cli(sys.argv[1:])
    else:
        main()
