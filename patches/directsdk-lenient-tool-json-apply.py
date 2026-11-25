#!/usr/bin/env python3
"""Local patch (2026-11-23) for the claude-subscription-directsdk plugin: keep tool calls whose streamed arguments
contain raw control characters.

The relay's Capture parses streamed tool input with strict json.loads. A complete call whose strings carry a literal
control character failed to parse and was dropped, so the request ended as "Native request failed: error_max_turns"
(stop_reason tool_use, no content blocks) on every retry. The parse is retried with strict=False, which accepts control
characters inside strings only; truncated or invalid JSON still fails and is still dropped.
Applies to the shared copy and every profile copy. Idempotent; `--check` only reports. `--test` runs the parse cases.
"""
import glob
import json
import os
import shutil
import sys

H = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
NAME = "plugins/claude-subscription-directsdk-experimental/admission.py"
FILES = [f for f in [f"{H}/{NAME}", *sorted(glob.glob(f"{H}/profiles/*/{NAME}"))] if os.path.exists(f)]
DONE = "json.loads(raw, strict=False)"  # also matches the first local version of this patch
OLD = """            try:
                self.message['content'][index]['input'] = json.loads(raw) if raw.strip() else {}
            except ValueError:
"""
NEW = """            try:
                try:
                    self.message['content'][index]['input'] = json.loads(raw) if raw.strip() else {}
                except ValueError:
                    # local patch (2026-11-23): streamed strings can carry raw control characters; truncated JSON still fails
                    self.message['content'][index]['input'] = json.loads(raw, strict=False)
            except ValueError:
"""

if "--test" in sys.argv:
    assert json.loads('{"a": "x\ty"}', strict=False) == {"a": "x\ty"}
    for bad in ('{"a": "x', '{"a": }'):
        try:
            json.loads(bad, strict=False)
        except ValueError:
            continue
        raise AssertionError(bad)
    src = "def f(self, raw, index):\n        for _ in (1,):\n" + NEW + "                return 'dropped'\n"
    ns = {"json": json}
    exec(compile(src, "new", "exec"), ns)

    class Msg:
        message = {"content": [{}]}
    assert ns["f"](Msg, '{"a": "x\ty"}', 0) is None and Msg.message["content"][0]["input"] == {"a": "x\ty"}
    assert ns["f"](Msg, '{"a": "x', 0) == "dropped"
    print("selftest ok")
    sys.exit(0)

if not FILES:
    print("plugin not installed: nothing to patch")
    sys.exit(0)
bad = 0
for f in FILES:
    s = open(f, encoding="utf-8").read()
    if DONE in s:
        continue
    if "--check" in sys.argv or s.count(OLD) != 1:
        print(("missing: " if s.count(OLD) == 1 else "anchor not found: ") + f)
        bad = 1
        continue
    new = s.replace(OLD, NEW)
    compile(new, f, "exec")
    if not os.path.exists(f + ".bak-2026-11-23-lenient-json"):
        shutil.copy2(f, f + ".bak-2026-11-23-lenient-json")
    open(f, "w", encoding="utf-8").write(new)
    print("patched", f)
print("ok" if not bad else "incomplete")
sys.exit(bad)
