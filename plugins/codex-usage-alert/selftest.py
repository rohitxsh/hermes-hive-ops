"""Self-check for the alert logic, no Hermes needed: python3 selftest.py"""
import importlib.util
import os
import types
from datetime import datetime, timedelta, timezone

spec = importlib.util.spec_from_file_location("cua", os.path.join(os.path.dirname(os.path.abspath(__file__)), "__init__.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

W = lambda label, pct, scope="account": types.SimpleNamespace(
    label=label, used_percent=pct, scope=scope, reset_at=datetime(2026, 10, 22, 16, 45, tzinfo=timezone.utc))
snap = lambda *w, age=0: types.SimpleNamespace(windows=w, fetched_at=datetime.now(timezone.utc) - timedelta(seconds=age))


def run(s):
    m._state.update(at=float("-inf"), snap=None)
    m._fetch = lambda: s
    return m.transform_llm_output(response_text="hi")


assert run(snap(W("Session", 69), W("Weekly", 13))) is None
out = run(snap(W("Session", 90), W("Weekly", 13)))
assert out.startswith("hi\n\n⚠️") and f"5-hour limit 90% used, resets {datetime(2026, 10, 22, 16, 45, tzinfo=timezone.utc).astimezone():%a %d %b %H:%M %Z}" in out and "weekly" not in out, out
out = run(snap(W("Session", 95), W("Weekly", 99.6)))
assert "5-hour limit 95%" in out and "weekly limit 100% used" in out, out
assert run(snap(W("Opus", 99, scope="model"))) is None          # model-only windows never alert
assert run(snap(W("Session", 95), age=20 * 60)) is None          # stale snapshot
assert run(None) is None                                          # fetch returned nothing
m._state.update(at=float("-inf"), snap=None)
m._fetch = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
assert m.transform_llm_output(response_text="hi") is None         # fetch error fails open
assert m.transform_llm_output(response_text="") is None
print("selftest ok")
