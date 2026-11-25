"""Local camofox patch (2026-11-20): mask password values in accessibility snapshots.
Playwright's ariaSnapshot prints a textbox's current value, including <input type=password>, so after a vault fill
the password landed in the agent's snapshot and transcript. This wraps getAriaSnapshot(): it reads the
values of every password input in every frame and replaces them (raw and YAML/JSON-escaped forms) with ********.
Re-run after `npm update` in ~/camofox, then restart agent-worker@camofox when no browser work is running.
Test: camofox-password-mask-test.sh"""
import os

p = os.path.expanduser("~/camofox/node_modules/@askjo/camofox-browser/server.js")
MARK = "local patch (2026-11-20): mask password values in snapshots"
old = "async function getAriaSnapshot(page) {\n"
new = f"""// {MARK}
async function _passwordValues(page) {{
  const values = new Set();
  for (const frame of page.frames()) {{
    try {{
      const vals = await Promise.race([
        frame.evaluate(() => Array.from(document.querySelectorAll('input[type="password" i]'))
          .map(e => e.value).filter(v => typeof v === 'string' && v.length > 0)),
        new Promise(resolve => setTimeout(() => resolve([]), 1500)),
      ]);
      for (const v of vals || []) values.add(v);
    }} catch {{ /* frame gone or cross-origin: skip */ }}
  }}
  return values;
}}

function _maskSecrets(yaml, values) {{
  if (!yaml || !values || values.size === 0) return yaml;
  let out = yaml;
  const forms = new Set();
  for (const v of values) {{
    forms.add(v);
    forms.add(JSON.stringify(v).slice(1, -1));
    forms.add(v.replace(/'/g, "''"));
  }}
  // longest first so a value that contains another is masked whole
  for (const f of Array.from(forms).filter(Boolean).sort((a, b) => b.length - a.length)) {{
    out = out.split(f).join('********');
  }}
  return out;
}}

async function getAriaSnapshot(page) {{
  const yaml = await _getAriaSnapshotUnmasked(page);
  if (!yaml || !page || page.isClosed()) return yaml;
  let values;
  try {{
    values = await _passwordValues(page);
  }} catch (err) {{
    log('warn', 'password mask: could not read password fields', {{ error: err.message }});
    return yaml.replace(/^(\\s*- textbox[^\\n]*?):\\s.*$/gim, '$1: [value hidden]');
  }}
  return _maskSecrets(yaml, values);
}}

async function _getAriaSnapshotUnmasked(page) {{
"""
s = open(p).read()
if MARK in s:
    print("already patched")
else:
    assert s.count(old) == 1, s.count(old)
    bak = p + ".bak-2026-11-20-pwmask"
    if not os.path.exists(bak):
        open(bak, "w").write(s)
    open(p, "w").write(s.replace(old, new))
    print("patched")
