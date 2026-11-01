import importlib.util
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import quota_lib as q  # noqa: E402

spec = importlib.util.spec_from_file_location("qa", os.path.join(here, "..", "..", "plugins", "quota-alert", "__init__.py"))
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)

W = q._window
c = ["openai-codex", "claude-subscription-directsdk-experimental", "nous"]
fine = [W("5-hour", 10, None), W("weekly", 20, None)]
hot = [W("5-hour", 92, "2026-10-25T21:31:00+00:00"), W("weekly", 50, None)]
week_out = [W("5-hour", 3, None), W("weekly", 100, "2026-10-30T18:00:00+00:00")]
claude = [W("5-hour", 40, None), W("weekly", 20, None)]


def g(table):
    return lambda p: table.get("claude" if q.is_claude(p) else p)


assert qa.alert_line(c, g({"openai-codex": fine}), False, q) is None
assert "5-hour 92% used" in qa.alert_line(c, g({"openai-codex": hot}), False, q)
line = qa.alert_line(c, g({"openai-codex": week_out, "claude": claude}), True, q)
assert "weekly limit reached" in line and "Claude: 5-hour 40% used (60% left)" in line and "Auto mode pauses at 70%" in line, line
line = qa.alert_line(c, g({"openai-codex": week_out, "claude": [W("5-hour", 100, None)]}), False, q)
assert "used up too" in line and "Nous" in line, line
assert qa.alert_line(c, g({}), False, q) is None
print("quota-alert selftest ok")
