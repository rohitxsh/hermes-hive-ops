"""token-usage: send "tokens" (or /tokens) in any chat to get this machine's model token use, lifetime and last 30 days,
from every profile's session history. Answered by the gateway itself: no model call, so it costs nothing and works
even when every provider is used up. Counts every call Hermes made (chats, cron, compression, approval checks)."""
from __future__ import annotations

import glob
import os
import socket
import sqlite3
import time
from collections import Counter

H = os.path.expanduser("~/.hermes")
NAMES = {"openai-codex": "ChatGPT", "claude-subscription-directsdk-experimental": "Claude", "openrouter": "OpenRouter",
         "nous": "Nous", "vertex": "Vertex"}
SQL = ("select billing_provider, coalesce(input_tokens,0), coalesce(cache_read_tokens,0) + coalesce(cache_write_tokens,0), "
       "coalesce(output_tokens,0), coalesce(last_seen, first_seen, 0) from session_model_usage")


def _rows(home=None):
    base = home or H
    for name, db in [("default", os.path.join(base, "state.db"))] + \
            [(os.path.basename(os.path.dirname(p)), p) for p in sorted(glob.glob(os.path.join(base, "profiles", "*", "state.db")))]:
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            for row in con.execute(SQL):
                yield (name,) + tuple(row)
            con.close()
        except sqlite3.Error:
            continue


def _fmt(n):
    return f"{n / 1e9:.2f}B" if n >= 1e9 else f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.1f}k" if n >= 1e3 else str(n)


def report(home=None, now=None):
    now = now or time.time()
    cutoff = now - 30 * 86400
    life, month = Counter(), Counter()
    by_provider, by_profile = Counter(), Counter()
    for profile, provider, fresh, cached, out, seen in _rows(home):
        total = fresh + cached + out
        life.update(total=total, fresh=fresh, cached=cached, out=out)
        if seen >= cutoff:
            month.update(total=total, fresh=fresh, cached=cached, out=out)
            by_provider[NAMES.get(provider or "", provider or "other")] += total
            by_profile[profile] += total

    def line(label, c):
        return (f"**{label}:** {_fmt(c['total'])} tokens (input {_fmt(c['fresh'])} new + {_fmt(c['cached'])} cached, "
                f"output {_fmt(c['out'])})")

    parts = [f"🔢 Model tokens on {socket.gethostname()} (all profiles)", line("Lifetime", life), line("Last 30 days", month)]
    if by_provider:
        parts.append("30 days by provider: " + " · ".join(f"{p} {_fmt(t)}" for p, t in by_provider.most_common()))
        parts.append("30 days by profile: " + " · ".join(f"{p} {_fmt(t)}" for p, t in by_profile.most_common(5)))
    return "\n".join(parts)


def _command(raw_args: str = "", **_kwargs):
    return report()


def _rewrite(event=None, **_kwargs):
    """A message that is just "tokens" becomes the /tokens command (answered without a model call)."""
    text = (getattr(event, "text", "") or "").strip().strip("?!. ").lower()
    if text == "tokens":
        return {"action": "rewrite", "text": "/tokens"}
    return None


def register(ctx):
    ctx.register_command("tokens", _command, description="Model token use on this machine: lifetime and last 30 days")
    ctx.register_hook("pre_gateway_dispatch", _rewrite)


def selftest():
    import tempfile
    base = tempfile.mkdtemp()
    __import__('atexit').register(__import__('shutil').rmtree, base, True)  # selftest leaves nothing in /tmp
    os.makedirs(os.path.join(base, "profiles", "jobs"))
    now = 2_000_000_000.0
    for db, rows in ((os.path.join(base, "state.db"), [("openai-codex", 1000, 8000, 1000, now - 86400)]),
                     (os.path.join(base, "profiles", "jobs", "state.db"), [("claude-subscription-directsdk-experimental", 500, 0, 500, now - 40 * 86400)])):
        con = sqlite3.connect(db)
        con.execute("create table session_model_usage (billing_provider text, input_tokens int, cache_read_tokens int, "
                    "cache_write_tokens int, output_tokens int, first_seen real, last_seen real)")
        for p, i, cr, o, seen in rows:
            con.execute("insert into session_model_usage values (?,?,?,?,?,?,?)", (p, i, cr, 0, o, seen, seen))
        con.commit()
        con.close()
    r = report(base, now)
    assert "**Lifetime:** 11.0k tokens" in r and "**Last 30 days:** 10.0k tokens" in r and "ChatGPT 10.0k" in r and "Claude" not in r.split("provider:")[1], r
    assert _rewrite(type("E", (), {"text": " Tokens? "})()) == {"action": "rewrite", "text": "/tokens"}
    assert _rewrite(type("E", (), {"text": "how many tokens did I use"})()) is None
    print("token-usage selftest ok")
