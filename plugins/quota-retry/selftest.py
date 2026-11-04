"""quota-retry self-test: a temporary state.db with Hermes's real messages/sessions schema, a fake inject_message and
fake quota. Run with Hermes's venv python from the Hermes checkout (the gateway-detection check uses gateway.status):
    cd ~/.hermes/hermes-agent && <venv>/bin/python ~/.hermes/plugins/quota-retry/selftest.py"""
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, ".")
spec = importlib.util.spec_from_file_location("qr", Path(__file__).with_name("__init__.py"))
qr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qr)

# copied from `.schema messages` / `.schema sessions` of a v0.22.6 state.db
SCHEMA = """
CREATE TABLE sessions (id TEXT PRIMARY KEY, runtime_revision INTEGER NOT NULL DEFAULT 0, runtime_generation INTEGER NOT NULL DEFAULT 0,
 source TEXT NOT NULL, created_source TEXT, user_id TEXT, session_key TEXT, chat_id TEXT, chat_type TEXT, thread_id TEXT,
 display_name TEXT, origin_json TEXT, expiry_finalized INTEGER DEFAULT 0, model TEXT, model_config TEXT, system_prompt TEXT,
 system_prompt_hash TEXT, parent_session_id TEXT, started_at REAL NOT NULL, ended_at REAL, end_reason TEXT,
 message_count INTEGER DEFAULT 0, tool_call_count INTEGER DEFAULT 0, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
 cache_read_tokens INTEGER DEFAULT 0, cache_write_tokens INTEGER DEFAULT 0, reasoning_tokens INTEGER DEFAULT 0, cwd TEXT,
 git_branch TEXT, git_repo_root TEXT, git_metadata_generation INTEGER NOT NULL DEFAULT 0, billing_provider TEXT,
 billing_base_url TEXT, billing_mode TEXT, estimated_cost_usd REAL, actual_cost_usd REAL, cost_status TEXT, cost_source TEXT,
 pricing_version TEXT, title TEXT, title_source TEXT, last_activity_at REAL, last_activity_description TEXT,
 last_activity_provenance TEXT, api_call_count INTEGER DEFAULT 0, handoff_state TEXT, handoff_platform TEXT, handoff_error TEXT,
 compression_failure_cooldown_until REAL, compression_failure_error TEXT, compression_fallback_streak INTEGER NOT NULL DEFAULT 0,
 compression_ineffective_count INTEGER NOT NULL DEFAULT 0, compression_recovery_deadline REAL,
 compression_overload_streak INTEGER NOT NULL DEFAULT 0, profile_name TEXT, transport_profile TEXT,
 rewind_count INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0, auto_archived INTEGER NOT NULL DEFAULT 0,
 pinned INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0, last_read_at REAL, tool_names TEXT,
 transcript_revision INTEGER NOT NULL DEFAULT 0, FOREIGN KEY (parent_session_id) REFERENCES sessions(id),
 FOREIGN KEY (system_prompt_hash) REFERENCES system_prompts(hash));
CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id), role TEXT NOT NULL,
 content TEXT, tool_call_id TEXT, tool_calls TEXT, tool_name TEXT, effect_disposition TEXT, timestamp REAL NOT NULL,
 token_count INTEGER, finish_reason TEXT, reasoning TEXT, reasoning_content TEXT, reasoning_details TEXT,
 codex_reasoning_items TEXT, codex_message_items TEXT, platform_message_id TEXT, observed INTEGER DEFAULT 0,
 _compressed_summary INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, compacted INTEGER NOT NULL DEFAULT 0,
 api_content TEXT, display_kind TEXT, display_metadata TEXT, display_identity BLOB, display_order INTEGER, message_uid TEXT,
 absorbed_message_uids TEXT, tool_call_uids TEXT, tool_call_uid TEXT);
"""
Q429 = "HTTP 429: upstream said: This request would exceed your account's rate limit. You've hit your session limit"
NOW = time.time()


def build(home):
    db = sqlite3.connect(os.path.join(home, "state.db"))
    db.executescript(SCHEMA)
    t = NOW - 3600

    def session(sid, key, source="discord"):
        db.execute("INSERT INTO sessions (id, source, session_key, started_at) VALUES (?, ?, ?, ?)", (sid, source, key, t - 99))

    def msg(sid, role, content="", kind=None, err=None, tool_calls=None, at=None):
        db.execute("INSERT INTO messages (session_id, role, content, timestamp, display_kind, display_metadata, tool_calls) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)", (sid, role, content, at or t, kind,
                                                     json.dumps({"error": err}) if err else None, tool_calls))
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]

    ids = {}
    session("plain", "agent:p:discord:group:1:2")       # nothing ran: retry
    msg("plain", "user", "please summarise the doc")
    ids["plain"] = msg("plain", "assistant", "Your request was not processed.", "failed_turn", Q429)
    session("tools", "agent:p:discord:group:3:2")       # tools ran: ask
    msg("tools", "user", "build the release " + "x" * 200)
    msg("tools", "assistant", "", tool_calls='[{"id": "c1"}]')
    msg("tools", "tool", '{"output": "ok"}')
    ids["tools"] = msg("tools", "assistant", "This turn did not complete.", "failed_turn", "HTTP 402: insufficient credit")
    session("other", "agent:p:discord:group:4:2")       # not a quota error: ignored
    msg("other", "user", "hello")
    msg("other", "assistant", "Your request was not processed.", "failed_turn", "HTTP 500: internal server error")
    session("mach", "agent:p:discord:group:5:2")        # machinery trigger: ignored
    msg("mach", "user", "[kanban] Task t_1 completed.", "internal_notification")
    msg("mach", "assistant", "Your request was not processed.", "failed_turn", Q429)
    session("resent", "agent:p:discord:group:6:2")      # person sent again: skipped
    msg("resent", "user", "first try")
    msg("resent", "assistant", "Your request was not processed.", "failed_turn", Q429)
    msg("resent", "user", "second try")
    session("busy", "agent:p:discord:group:8:2")        # only a machinery notice was answered since: still retried
    msg("busy", "user", "what about the budget")
    ids["busy"] = msg("busy", "assistant", "Your request was not processed.", "failed_turn", "usage limit reached")
    msg("busy", "user", "[kanban] Task t_2 completed.", "internal_notification")
    msg("busy", "assistant", "Task t_2 is done.")
    session("old", "agent:p:discord:group:7:2")         # 30 h old: expired
    msg("old", "user", "old question", at=NOW - 30 * 3600)
    ids["old"] = msg("old", "assistant", "Your request was not processed.", "failed_turn", Q429, at=NOW - 30 * 3600)
    session("cron", None)                               # no session key (subagent/cron): ignored
    msg("cron", "user", "subagent goal")
    msg("cron", "assistant", "failed", "failed_turn", Q429)
    session("kanban", "agent:p:kanban:t_1", "kanban")    # Kanban worker session (not a chat): ignored
    msg("kanban", "user", "# Kanban task t_1")
    msg("kanban", "assistant", "failed", "failed_turn", Q429)
    db.commit()
    db.close()
    return ids


def matcher():
    yes = [Q429, "HTTP 404: Model 'x' requires available credits. Your account balance is too low",
           "Rate limit exceeded", "HTTP 402 Payment Required", "quota exceeded for this month", "usage limit reached"]
    no = ["HTTP 500: internal server error", "Connection reset by peer", "context length exceeded", "HTTP 4290 at port", ""]
    assert all(qr.is_quota_error(e) for e in yes), [e for e in yes if not qr.is_quota_error(e)]
    assert not any(qr.is_quota_error(e) for e in no), [e for e in no if qr.is_quota_error(e)]


def append(home, sid, *rows):
    """Rows Hermes would write after our injection: (role, content, display_kind, error, timestamp)."""
    db = sqlite3.connect(os.path.join(home, "state.db"))
    for role, content, kind, err, at in rows:
        db.execute("INSERT INTO messages (session_id, role, content, timestamp, display_kind, display_metadata) "
                   "VALUES (?, ?, ?, ?, ?, ?)", (sid, role, content, at, kind, json.dumps({"error": err}) if err else None))
    db.commit()
    db.close()


def availability():
    """quota_back with a fake quota_lib: known usage below its limit, or unknown and no failure since the turn."""
    use, fails = {}, {}
    sys.modules["quota_lib"] = types.SimpleNamespace(
        FAIL_WINDOW=3600, chain=lambda h: ["openai-codex", "nous"], usage=lambda p: use.get(p),
        profile_usage=lambda h, getu: getu, provider_name=lambda p: p, describe=lambda w: str(w),
        used_up=lambda w: [x for x in w or [] if x["used"] >= 99.5],
        recent_failures=lambda h, now: {p: t for p, t in fails.items() if now - t < 3600})  # quota_lib's own filter
    since = NOW - 600
    use["openai-codex"] = [{"label": "5-hour", "used": 100.0}]
    fails["nous"] = NOW - 5000                   # unknown usage, failed only before the turn
    assert qr.quota_back("h", since) == (False, "waiting: only unknown-usage providers available")   # default: wait
    assert qr.quota_back("h", since, True) == (True, "nous is back (usage unknown, trusted)")      # trusted: back
    fails["nous"] = NOW - 300                    # unknown usage, failed after the turn started: not back even trusted
    assert qr.quota_back("h", since, True)[0] is False
    assert qr.quota_back("h", NOW - 3 * 3600, True)[0] is False   # failed long after since (outside quota_lib's 1 h)
    use["openai-codex"] = [{"label": "5-hour", "used": 3.0}]   # known provider reset: back, trusted or not
    ok, why = qr.quota_back("h", since)
    assert ok is True and why.startswith("openai-codex"), why
    sys.modules["quota_lib"] = None              # quota_lib missing: unknown (and logged)
    assert qr.quota_back("h", since)[0] is None
    del sys.modules["quota_lib"]


def main():
    matcher()
    availability()
    home = tempfile.mkdtemp()
    ids = build(home)
    sent = []
    inject = lambda content, role="user", *, session_key=None, origin=None: sent.append((session_key, content)) or True

    qr.quota_back = lambda h, since, trust=False: (False, "every provider in the chain is used up")
    acts = qr.tick(home, inject, False, now=NOW)
    assert not sent and {d for d, _, _ in acts} == {"waiting"}, acts           # quota still out: nothing
    assert not os.path.exists(os.path.join(home, qr.STATE))

    qr.quota_back = lambda h, since, trust=False: (True, "Claude would answer")
    acts = qr.tick(home, inject, True, now=NOW)                                 # dry run: decisions, nothing sent or saved
    assert not sent and not os.path.exists(os.path.join(home, qr.STATE))
    assert {c["id"]: d for d, c, _ in acts} == {ids["plain"]: "retry", ids["tools"]: "ask", ids["busy"]: "retry",
                                                ids["old"]: "expired"}, acts

    acts = qr.tick(home, inject, False, now=NOW)
    keys = {k: c for k, c in sent}
    assert set(keys) == {"agent:p:discord:group:1:2", "agent:p:discord:group:3:2", "agent:p:discord:group:8:2"}, sent
    plain = keys["agent:p:discord:group:1:2"]
    assert plain.startswith("[Automatic retry: your message from ") and plain.endswith("\n\nplease summarise the doc"), plain
    ask = keys["agent:p:discord:group:3:2"]
    assert "Do not redo" in ask and "x" * 200 not in ask and ("build the release " + "x" * 81 + "…") in ask, ask
    assert "agent:p:discord:group:7:2" not in keys                              # expired: nothing injected
    state = json.load(open(os.path.join(home, qr.STATE)))["handled"]
    assert state[str(ids["old"])]["decision"] == "expired" and state[str(ids["plain"])]["decision"] == "retry"

    n = len(sent)
    assert qr.tick(home, inject, False, now=NOW + 180) == [] and len(sent) == n  # second tick: no repeat

    # our retry fails on quota: the original goes back to pending and is retried; the third failure gives up
    st = lambda k: json.load(open(os.path.join(home, qr.STATE)))["handled"][str(ids[k])]
    append(home, "busy", ("user", "[Alex] " + keys["agent:p:discord:group:8:2"], "internal_notification", None, NOW + 20),
           ("assistant", "Here is the budget.", None, None, NOW + 21))          # busy: our retry was answered
    for attempt, at in ((1, NOW + 10), (2, NOW + 210), (3, NOW + 410)):
        append(home, "plain", ("user", "[Alex] " + plain, None, None, at),     # stored like a human row: worst case
               ("assistant", "Your request was not processed.", "failed_turn", Q429, at + 1))
        before = len(sent)
        qr.tick(home, inject, False, now=at + 190)
        if attempt < 3:
            assert len(sent) == before + 1 and sent[-1] == ("agent:p:discord:group:1:2", plain), sent[before:]
            assert st("plain")["status"] == "injected" and st("plain")["attempts"] == attempt + 1
        else:
            assert len(sent) == before and st("plain")["status"] == "gave_up" and st("plain")["attempts"] == 3
    assert st("busy")["status"] == "done" and st("busy")["attempts"] == 1
    before = len(sent)
    assert qr.tick(home, inject, False, now=NOW + 800) == [] and len(sent) == before   # gave up: nothing more
    qr.tick(home, inject, False, now=NOW + 2000)   # the ask-note never showed up in the session: asked again
    assert sent[before:] == [("agent:p:discord:group:3:2", ask)] and st("tools")["attempts"] == 2, sent[before:]

    # rate cap, and a refused injection is retried on the next scan
    home2 = tempfile.mkdtemp()
    build(home2)
    qr.MAX_PER_TICK = 1
    refused = qr.tick(home2, lambda *a, **k: False, False, now=NOW)
    assert sum(d in ("retry", "ask") for d, _, _ in refused) == 1, refused
    assert [v["decision"] for v in json.load(open(os.path.join(home2, qr.STATE)))["handled"].values()] == ["expired"]
    sent2 = []
    qr.tick(home2, lambda c, role="user", **k: sent2.append(k["session_key"]) or True, False, now=NOW)
    assert len(sent2) == 1, sent2
    qr.MAX_PER_TICK = 3

    # quota_lib can't tell: retried only an hour after the failure
    home3 = tempfile.mkdtemp()
    build(home3)
    qr.quota_back = lambda h, since, trust=False: (None, "quota unknown")
    assert {d for d, _, _ in qr.tick(home3, inject, True, now=NOW - 1800)} <= {"waiting", "expired"}
    assert "retry" in {d for d, _, _ in qr.tick(home3, inject, True, now=NOW + 60)}

    # gateway detection: no loop outside the gateway process
    started = []
    ctx = type("Ctx", (), {"on_unload": lambda self, f: started.append(f), "inject_message": inject})()
    before = threading.active_count()
    for argv in (["-c", "chat", "-q", "hi"], ["/usr/bin/hermes", "cron", "tick"], ["-c", "kanban", "work"], ["-c", "gateway", "status"]):
        sys.argv = argv
        qr.register(ctx)
    assert threading.active_count() == before and not started, "a loop started outside the gateway"
    sys.argv = ["-c", "gateway", "run", "--replace", "--external-supervisor"]
    qr.register(ctx)
    assert threading.active_count() == before + 1 and len(started) == 1
    started[0]()                                                                # on_unload stops it
    time.sleep(0.2)
    assert threading.active_count() == before
    print("selftest ok")


main()
