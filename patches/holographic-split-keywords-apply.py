#!/usr/bin/python3
"""Local patch (2026-11-18) for the holographic memory plugin (third-party, itpartypattaya/hermes-plugin-holographic
0.26.x): its keyword screen joined a fact's keywords with commas before checking them for instructions, so an
instruction split across keywords ("ignore", "previous", "instructions") passed while the same words in one keyword
were refused. The screen now also checks the space-joined form. Storage is unchanged; only more is refused.
Applies to the shared copy and every profile copy. Idempotent; `--check` only reports. Re-run after a plugin update."""
import glob
import re
import shutil
import sys
from pathlib import Path

H = Path.home()
TAG = ".bak-2026-11-18-split-keywords"
MARK = "local patch (2026-11-18): also screen the space-joined keywords"
LINE = re.compile(r'^(?P<i>[ \t]+)problem = _fact_problem\(", "\.join\((?P<v>\w+)\)\) if (?P=v) else ""\n', re.M)


def files():
    return [Path(p) for p in [str(H / ".hermes/plugins/holographic/__init__.py")]
            + sorted(glob.glob(str(H / ".hermes/profiles/*/plugins/holographic/__init__.py"))) if Path(p).exists()]


def patch(s):
    k = s.find("def _keyword_problem(")
    if k < 0 or MARK in s:
        return s
    m = LINE.search(s, k)
    assert m and m.start() - k < 1200, "keyword screen line not found in _keyword_problem; plugin changed, patch by hand"
    i, v = m["i"], m["v"]
    new = (f'{i}# {MARK} (an instruction split across keywords)\n'
           f'{i}problem = (_fact_problem(", ".join({v})) or _fact_problem(" ".join({v}))) if {v} else ""\n')
    return s[:m.start()] + new + s[m.end():]


def selftest():
    a = 'x\n    def _keyword_problem(a):\n        keywords = k(a)\n        problem = _fact_problem(", ".join(keywords)) if keywords else ""\n        return problem\n'
    b = patch(a)
    assert MARK in b and '_fact_problem(" ".join(keywords))' in b and patch(b) == b
    print("selftest ok")


def fixed(s):
    return MARK in s or '_fact_problem(" ".join(' in s  # a hand fix with the same check counts


if "--test" in sys.argv:
    selftest(); sys.exit(0)
missing = [f for f in files() if not fixed(f.read_text(encoding="utf-8"))]
if "--check" in sys.argv:
    print("ok" if not missing else f"missing in {len(missing)} copies")
    sys.exit(0 if not missing else 1)
for f in missing:
    s = f.read_text(encoding="utf-8")
    n = patch(s)
    compile(n, str(f), "exec")
    if not Path(str(f) + TAG).exists():
        shutil.copy2(f, str(f) + TAG)
    f.write_text(n, encoding="utf-8")
    print("patched", f)
print("ok")
