"""quota-retry: answer chat messages that failed because every model provider was out of quota, once quota is back.

Inside the gateway only, one background loop per profile checks the profile's state.db every 3 minutes for failed
turns (display_kind 'failed_turn') whose error is a quota / rate-limit / credit error, in a messaging session, started
by a human message that nobody has followed up since (no newer human message, no reply to one). When quota_lib says
a provider is back (usage known and below its limit; with trust_unknown_usage: true also a provider whose usage
quota_lib can't read and that has not failed since the failed turn started), each failure is handled (state in <home>/quota-retry-state.json):
- nothing ran before the failure: the original message is injected again, after a one-line note;
- tools had run: a note asks the agent to tell the person the request stopped partway and ask whether to redo it;
- older than MAX_AGE: nothing is injected, it is only recorded as expired.
It counts as done only once the session shows a reply after our message. If our turn fails on quota again (or never
shows up), the original goes back to pending, up to MAX_ATTEMPTS injections, then it is recorded as gave_up.
Turns are started with ctx.inject_message(session_key=...), which needs
plugins.entries.quota-retry.allow_gateway_injection: true. plugins.entries.quota-retry.dry_run: true only logs.
Test scan, injects and writes nothing:  python3 __init__.py --scan [--home ~/.hermes/profiles/NAME]
"""
from __future__ import annotations

import json
import logging
import os
import re
import shlex
import sqlite3
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/agents/src/quota"))

PLUGIN = "quota-retry"
INTERVAL = 180            # seconds between scans
FIRST_DELAY = 60          # let the gateway finish starting before the first scan
MAX_AGE = 24 * 3600       # failures older than this when quota comes back are not retried
MAX_PER_TICK = 3          # injections per profile per scan
UNKNOWN_QUOTA_WAIT = 3600  # without quota_lib: treat quota as back this long after the failure
MAX_ATTEMPTS = 3          # injections per original message before giving up
WAIT_LOG_EVERY = 3600     # "waiting" reasons are logged at most this often per failed turn
LOST_AFTER = 1800         # an accepted injection that never shows up in the session after this counts as failed
STATE = "quota-retry-state.json"
PREFIX = "[Automatic retry"
QUOTA_ERROR = re.compile(r"\b(?:429|402)\b|rate.?limit|session limit|usage limit|quota|credit|insufficient", re.I)
log = logging.getLogger(__name__)
_wait_logged: dict = {}   # (home, failed turn id) -> when its waiting reason was last logged


def is_quota_error(text: str) -> bool:
    return bool(QUOTA_ERROR.search(text or ""))


def _error(meta) -> str:
    try:
        return str((json.loads(meta or "{}") or {}).get("error") or "")
    except (ValueError, AttributeError):
        return ""


def _connect(home: str):
    return sqlite3.connect(f"file:{os.path.join(home, 'state.db')}?mode=ro", uri=True, timeout=10)


def _profile(home: str) -> str:
    home = os.path.realpath(home)
    return "default" if home == os.path.realpath(os.path.expanduser("~/.hermes")) else os.path.basename(home)


def _messaging_sources() -> list[str]:
    """Hermes's gateway platforms that are human chat channels (not cron, kanban, oneshot, subagent, local, ...)."""
    try:
        from gateway.config import Platform
        from gateway.session_context import NON_MESSAGING_SESSION_SURFACES
        return sorted({p.value for p in Platform} - NON_MESSAGING_SESSION_SURFACES)
    except Exception:
        return ["discord", "telegram", "slack", "whatsapp", "signal", "matrix", "mattermost"]


def candidates(home: str, now: float, max_age: float = MAX_AGE) -> list[dict]:
    """Unanswered human messages whose turn failed on quota, within 2 * max_age (older ones become 'expired')."""
    sources = _messaging_sources()
    db = _connect(home)
    try:
        failures = db.execute(
            "SELECT m.id, m.session_id, m.timestamp, m.display_metadata, s.session_key FROM messages m "
            "JOIN sessions s ON s.id = m.session_id WHERE m.role = 'assistant' AND m.display_kind = 'failed_turn' "
            "AND m.active = 1 AND m.timestamp > ? AND COALESCE(s.session_key, '') != '' "
            f"AND s.source IN ({','.join('?' * len(sources))}) ORDER BY m.id", (now - 2 * max_age, *sources)).fetchall()
        out = []
        for fid, sid, ts, meta, key in failures:
            if not is_quota_error(_error(meta)):
                continue
            trig = db.execute("SELECT id, content, display_kind, timestamp FROM messages WHERE session_id = ? AND id < ? "
                              "AND role = 'user' AND active = 1 ORDER BY id DESC LIMIT 1", (sid, fid)).fetchone()
            # human = no display kind (machinery: internal_notification, hidden, steer, ...); never our own retries
            if not trig or trig[2] is not None or not (trig[1] or "").strip() or PREFIX in trig[1]:
                continue
            ran = db.execute("SELECT 1 FROM messages WHERE session_id = ? AND id > ? AND id < ? AND active = 1 AND "
                             "(role = 'tool' OR (role = 'assistant' AND tool_calls IS NOT NULL)) LIMIT 1",
                             (sid, trig[0], fid)).fetchone()
            # moved on: a newer human message under this session key (also in a rotated session), or a reply to one;
            # our own injected retries are neither
            newer = db.execute(
                "SELECT 1 FROM messages m JOIN sessions s ON s.id = m.session_id WHERE s.session_key = ? "
                "AND m.active = 1 AND m.role = 'user' AND m.display_kind IS NULL AND instr(COALESCE(m.content, ''), ?) = 0 "
                "AND ((m.session_id = ? AND m.id > ?) OR (m.session_id != ? AND m.timestamp > ?)) LIMIT 1",
                (key, PREFIX, sid, fid, sid, ts)).fetchone() or db.execute(
                "SELECT 1 FROM messages a WHERE a.session_id = ? AND a.id > ? AND a.active = 1 AND a.role = 'assistant' "
                "AND a.display_kind IS NULL AND (SELECT u.display_kind IS NULL AND instr(COALESCE(u.content, ''), ?) = 0 "
                "FROM messages u WHERE u.session_id = a.session_id AND u.id < a.id AND u.role = 'user' AND u.active = 1 "
                "ORDER BY u.id DESC LIMIT 1)", (sid, fid, PREFIX)).fetchone()
            if not newer:
                out.append({"id": fid, "session_id": sid, "session_key": key, "at": ts, "since": trig[3],
                            "text": trig[1], "ran": bool(ran)})
        return out
    finally:
        db.close()


def quota_back(home: str, since: float, trust_unknown: bool = False):
    """(True/False, why): some provider in the profile's chain is back for a turn that failed after ``since`` (when
    the failed turn started; provider failures are logged before the failed_turn row). Back = usage known and below
    its limit, or (only with ``trust_unknown``) usage unknown and no failure in quota_lib's records since then.
    (None, why) without quota_lib."""
    try:
        import quota_lib as q
        providers = q.chain(home)
        if not providers:
            return True, "no model chain configured"
        getu = q.profile_usage(home, lambda p: q.usage(p))
        failed = q.recent_failures(home, now=since + q.FAIL_WINDOW)  # its window ends at `now`: every failure after since
        unknown = False
        for p in providers:
            w = getu(p)
            if w is not None and not q.used_up(w):
                return True, f"{q.provider_name(p)} is back ({q.describe(w)})"
            if w is None and p not in failed:
                if trust_unknown:
                    return True, f"{q.provider_name(p)} is back (usage unknown, trusted)"
                unknown = True  # e.g. Nous out of credit: its usage can't be read and it may not have failed here
        return False, "waiting: only unknown-usage providers available" if unknown else "no provider in the chain is back yet"
    except Exception as exc:
        log.warning("quota-retry[%s]: quota_lib unavailable (%s); treating quota as back %d min after a failure",
                    _profile(home), str(exc)[:80], UNKNOWN_QUOTA_WAIT // 60)
        return None, "quota unknown"


def _outcome(db, key: str, injected_at: float, now: float):
    """What became of our injected message: (None | "ok" | "quota" | "failed" | "lost", tools_ran)."""
    r = db.execute("SELECT m.id, m.session_id FROM messages m JOIN sessions s ON s.id = m.session_id "
                   "WHERE s.session_key = ? AND m.role = 'user' AND m.active = 1 AND instr(COALESCE(m.content, ''), ?) > 0 "
                   "AND m.timestamp >= ? ORDER BY m.timestamp LIMIT 1", (key, PREFIX, injected_at - 60)).fetchone()
    if r is None:
        return ("lost" if now - injected_at > LOST_AFTER else None), False
    a = db.execute("SELECT id, display_kind, display_metadata FROM messages WHERE session_id = ? AND id > ? AND active = 1 "
                   "AND role = 'assistant' AND (display_kind = 'failed_turn' OR (display_kind IS NULL AND tool_calls IS NULL "
                   "AND COALESCE(content, '') != '')) ORDER BY id LIMIT 1", (r[1], r[0])).fetchone()
    if a is None:
        return None, False
    if a[1] is None:
        return "ok", False
    ran = db.execute("SELECT 1 FROM messages WHERE session_id = ? AND id > ? AND id < ? AND active = 1 AND "
                     "(role = 'tool' OR (role = 'assistant' AND tool_calls IS NOT NULL)) LIMIT 1", (r[1], r[0], a[0])).fetchone()
    return ("quota" if is_quota_error(_error(a[2])) else "failed"), bool(ran)


def follow_up(home: str, handled: dict, now: float) -> bool:
    """Settle injected messages: done after a reply, pending again after a quota failure, gave_up after MAX_ATTEMPTS."""
    live = {k: e for k, e in handled.items() if e.get("status") == "injected"}
    if not live:
        return False
    changed, db = False, _connect(home)
    try:
        for k, e in live.items():
            outcome, ran = _outcome(db, e["session_key"], e["injected_at"], now)
            if outcome is None:
                continue
            e["ran"] = bool(e.get("ran") or ran)  # tools ran in our turn: the next attempt only asks
            e["status"] = "done" if outcome == "ok" else \
                "pending" if outcome in ("quota", "lost") and e.get("attempts", 0) < MAX_ATTEMPTS else "gave_up"
            changed = True
            log.info("quota-retry[%s]: failed turn %s in session %s: our %s turn %s -> %s (attempt %d)",
                     _profile(home), k, e.get("session_id"), e.get("decision"), outcome, e["status"], e.get("attempts", 0))
    finally:
        db.close()
    return changed


def _when(ts: float, now: float) -> str:
    t, n = datetime.fromtimestamp(ts), datetime.fromtimestamp(now)
    return t.strftime("%H:%M") if t.date() == n.date() else t.strftime("%a %d %b %H:%M")


def message(c: dict, decision: str, now: float) -> str:
    when = _when(c["at"], now)
    if decision == "retry":
        return (f"{PREFIX}: your message from {when} failed because every model provider was out of quota. "
                f"Quota is back, so I'm answering it now.]\n\n{c['text']}")
    quote = " ".join(c["text"].split())
    quote = quote if len(quote) <= 100 else quote[:99] + "…"
    return (f"{PREFIX} note: the person's request from {when} (\"{quote}\") stopped partway because every model "
            "provider ran out of quota, and some of its steps may already have run. Do not redo any of it and do "
            "not run any tools for it now. In one short message, tell them that and ask whether they want you to "
            "redo it.]")


def load_state(home: str) -> dict:
    try:
        with open(os.path.join(home, STATE)) as fh:
            state = json.load(fh)
        return state if isinstance(state.get("handled"), dict) else {"handled": {}}
    except (OSError, ValueError, AttributeError):
        return {"handled": {}}


def save_state(home: str, state: dict) -> None:
    path = os.path.join(home, STATE)
    with open(path + ".tmp", "w") as fh:  # one loop per profile writes it; the rename keeps it whole
        json.dump(state, fh)
    os.replace(path + ".tmp", path)


def tick(home: str, inject, dry_run: bool, now: float | None = None, seen: set | None = None,
         max_age: float = MAX_AGE, trust_unknown: bool = False) -> list[tuple]:
    """One scan of this profile. Returns [(decision, candidate, why)]; decisions: retry, ask, expired, waiting."""
    now = now or time.time()
    state = load_state(home)
    handled = state["handled"]
    changed = not dry_run and follow_up(home, handled, now)
    found = [c for c in candidates(home, now, max_age)
             if handled.get(str(c["id"]), {}).get("status", "pending") == "pending"]
    profile, done, budget = _profile(home), [], MAX_PER_TICK
    for c in found:
        entry = handled.get(str(c["id"]), {})
        c["ran"] = c["ran"] or bool(entry.get("ran"))
        ok, why = quota_back(home, c["since"], trust_unknown)
        if ok is False or (ok is None and now - c["at"] < UNKNOWN_QUOTA_WAIT):
            done.append(("waiting", c, why))
            if now - _wait_logged.get((home, c["id"]), float("-inf")) >= WAIT_LOG_EVERY:
                _wait_logged[(home, c["id"])] = now
                log.info("quota-retry[%s]: failed turn %s in session %s: %s", profile, c["id"], c["session_id"], why)
            continue
        decision = "expired" if now - c["at"] > max_age else "ask" if c["ran"] else "retry"
        if decision != "expired":
            if budget <= 0:
                continue  # next scan
            budget -= 1
        done.append((decision, c, why))
        if dry_run:
            if seen is None or c["id"] not in seen:
                log.info("quota-retry[%s]: dry run: would %s failed turn %s in session %s (%s): %.100s",
                         profile, decision, c["id"], c["session_id"], why, " ".join(c["text"].split()))
            if seen is not None:
                seen.add(c["id"])
            continue
        if decision != "expired" and not inject(message(c, decision, now), role="user", session_key=c["session_key"]):
            log.warning("quota-retry[%s]: gateway did not accept the %s for session %s; trying again next scan",
                        profile, decision, c["session_id"])
            continue
        attempts = entry.get("attempts", 0) + (decision != "expired")
        handled[str(c["id"])] = {**entry, "status": "expired" if decision == "expired" else "injected",
                                 "decision": decision, "attempts": attempts, "failed_at": c["at"], "injected_at": now,
                                 "session_id": c["session_id"], "session_key": c["session_key"]}
        changed = True
        log.info("quota-retry[%s]: %s failed turn %s in session %s (attempt %d; %s)", profile,
                 {"retry": "retried", "ask": "asked about", "expired": "expired (not retried)"}[decision],
                 c["id"], c["session_id"], attempts, why)
    if changed:
        state["handled"] = {k: v for k, v in handled.items() if now - v.get("failed_at", now) < 3 * max_age}
        save_state(home, state)
    return done


def _options(home: str) -> tuple[bool, bool]:
    """(dry_run, trust_unknown_usage) from plugins.entries.quota-retry (or its settings) in the profile's config."""
    try:
        import yaml
        with open(os.path.join(home, "config.yaml")) as fh:
            entry = (((yaml.safe_load(fh) or {}).get("plugins") or {}).get("entries") or {}).get(PLUGIN) or {}
    except Exception:
        return True, False  # can't read the profile's config: don't act on it
    get = lambda k: entry.get(k, (entry.get("settings") or {}).get(k)) is True
    return get("dry_run"), get("trust_unknown_usage")


def _in_gateway() -> bool:
    """This process runs the messaging gateway (plugins also load in CLI, cron and Kanban worker processes)."""
    try:
        from gateway.status import looks_like_gateway_runtime_command_line
    except Exception:
        return False
    # Hermes's own matcher for gateway runtime command lines; under Hermes's launcher sys.argv[0] is "-c"
    return looks_like_gateway_runtime_command_line(shlex.join(["hermes", *sys.argv[1:]]))


def _loop(ctx, home: str, stop: threading.Event) -> None:
    seen: set = set()
    if stop.wait(FIRST_DELAY):
        return
    while True:
        try:
            dry_run, trust_unknown = _options(home)
            tick(home, ctx.inject_message, dry_run, seen=seen, trust_unknown=trust_unknown)
        except Exception as exc:
            log.warning("quota-retry[%s]: scan failed: %s", _profile(home), exc)
        if stop.wait(INTERVAL):
            return


def register(ctx) -> None:
    if not _in_gateway():
        return
    from hermes_constants import get_hermes_home
    home = str(get_hermes_home())  # the profile being loaded (register runs under its home)
    stop = threading.Event()
    ctx.on_unload(stop.set)
    threading.Thread(target=_loop, args=(ctx, home, stop), name=f"quota-retry-{_profile(home)}", daemon=True).start()
    log.info("quota-retry[%s]: started (every %ds)", _profile(home), INTERVAL)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="One dry-run scan: prints what quota-retry would do; changes nothing.")
    ap.add_argument("--scan", action="store_true", required=True)
    ap.add_argument("--home", default=os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"))
    ap.add_argument("--max-age-hours", type=float, default=MAX_AGE / 3600)
    a = ap.parse_args()
    now = time.time()
    acts = tick(a.home, None, True, now=now, max_age=a.max_age_hours * 3600, trust_unknown=_options(a.home)[1])
    print(f"{_profile(a.home)}: {len(acts)} pending" + ("" if acts else " (nothing to do)"))
    for d, c, why in acts:
        print(f"  {d:8} failed turn {c['id']} at {_when(c['at'], now)} session {c['session_id']} "
              f"[{'tools ran' if c['ran'] else 'nothing ran'}] ({why}): {' '.join(c['text'].split())[:100]}")
