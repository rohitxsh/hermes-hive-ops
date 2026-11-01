"""Local camofox patch (vm-a 2026-10-26): /tabs/:id/upload honours a selector that names a file input.
Upstream sets the page's FIRST <input type=file> whenever one exists, ignoring the selector, so on pages with a photo
input before the CV input (Instahyre) the CV went into the photo input. Re-run after `npm update` in ~/camofox, then
restart agent-worker@camofox when no browser work is running. Test: cv-upload --selftest."""
import os

p = os.path.expanduser("~/camofox/node_modules/@askjo/camofox-browser/server.js")
MARK = "local patch (vm-a 2026-10-26): upload selector first"
old = """      const directInput = tabState.page.locator('input[type="file"]').first();"""
new = (f"""      // {MARK}: a selector naming a file input wins over the page's first file input
      const named = selector ? tabState.page.locator(selector).first() : null;
      const namedIsInput = named
        ? await named.evaluate(el => el.tagName === 'INPUT' && el.type === 'file', null, {{ timeout: 2000 }}).catch(() => false)
        : false;
      const directInput = namedIsInput ? named : tabState.page.locator('input[type="file"]').first();""")
if not os.path.exists(p):
    print("camofox not installed: nothing to patch")
    raise SystemExit
s = open(p).read()
if MARK in s:
    print("already patched")
else:
    assert s.count(old) == 1, s.count(old)
    if not os.path.exists(p + ".bak-2026-10-26-upload"):
        open(p + ".bak-2026-10-26-upload", "w").write(s)
    open(p, "w").write(s.replace(old, new))
    print("patched")
