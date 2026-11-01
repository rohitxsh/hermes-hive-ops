// render.cjs <html-file> <png-out> <selector|""> <wait-ms>
// Screenshots a standalone HTML file at 1200x800, deviceScaleFactor 2, dark color scheme.
// Uses playwright-core (ARTIFACT_PLAYWRIGHT, else ~/agents/src/artifacts/node_modules, else ~/camofox) and
// Hermes's bundled Chromium (ARTIFACT_CHROME to override).
// The PNG is a static image in Discord, so by default controls are turned into their current state before the
// screenshot (sliders, dropdowns and inputs become their values, active buttons/tabs become plain labels, the rest
// is hidden, <details> open, chart toolbars hidden). ARTIFACT_KEEP_CONTROLS=1 keeps them (UI prototypes, where the
// controls are the design). ARTIFACT_BADGE=1 adds a small "interactive version attached" badge.
'use strict';
const fs = require('fs');
const path = require('path');
const os = require('os');

const PW = [process.env.ARTIFACT_PLAYWRIGHT,
  path.join(os.homedir(), 'agents/src/artifacts/node_modules/playwright-core'),
  path.join(os.homedir(), 'camofox/node_modules/playwright-core')].find(p => p && fs.existsSync(p));
const CHROME = process.env.ARTIFACT_CHROME ||
  path.join(os.homedir(), '.hermes/tools/chromium-1208/chrome-linux64/chrome');

// Runs in the page. Returns counts so publish-artifact's selftest can check the transform ran.
function staticPreview(badge) {
  const n = { replaced: 0, hidden: 0 };
  const doc = document;
  doc.documentElement.setAttribute('data-preview', 'png');
  doc.dispatchEvent(new CustomEvent('artifact-preview'));  // pages may switch to a static layout themselves
  const css = doc.createElement('style');
  css.textContent = `
    [data-interactive-only], .modebar-container, .modebar, .leaflet-control-container, .mapboxgl-ctrl,
    [role="tooltip"] { display: none !important; }
    summary { list-style: none; cursor: default; } summary::-webkit-details-marker { display: none; }
    .artifact-static { font: inherit; color: inherit; background: none !important; border: 0 !important;
      box-shadow: none !important; padding: 0 2px !important; cursor: default; }
    .artifact-static.value { color: #38bdf8; font-weight: 600; }
    .artifact-static.active { font-weight: 600; }
    #artifact-preview-badge { position: fixed; right: 12px; bottom: 10px; z-index: 2147483647; font: 12px/1.4
      system-ui, sans-serif; color: #94a3b8; background: rgba(15, 23, 42, .85); border: 1px solid #334155;
      border-radius: 6px; padding: 3px 8px; }`;
  doc.head.appendChild(css);
  const visible = el => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden'; };
  const kept = el => el.closest('[data-keep-in-preview]');
  const swap = (el, text, cls) => {
    const span = doc.createElement('span');
    span.className = 'artifact-static ' + cls;
    span.textContent = text;
    el.replaceWith(span);
    n.replaced++;
  };
  const hide = el => { el.style.setProperty('display', 'none', 'important'); n.hidden++; };
  doc.querySelectorAll('details').forEach(d => { d.open = true; });
  doc.querySelectorAll('select').forEach(el => {
    if (kept(el) || !visible(el)) return;
    const opts = [...el.selectedOptions].map(o => o.textContent.trim()).filter(Boolean);
    opts.length ? swap(el, opts.join(', '), 'value') : hide(el);
  });
  doc.querySelectorAll('input').forEach(el => {
    if (kept(el) || !visible(el)) return;
    const t = (el.type || 'text').toLowerCase();
    if (t === 'hidden') return;
    if (t === 'checkbox' || t === 'radio') {
      const label = el.closest('label');
      if (!el.checked && t === 'radio' && label) { hide(label); return; }  // only the chosen option stays
      swap(el, el.checked ? '✓' : '–', 'value');
    } else if (['button', 'submit', 'reset', 'image', 'file', 'color'].includes(t)) {
      hide(el);
    } else if (el.value !== '') {
      swap(el, el.value + (t === 'range' && el.dataset.unit ? ' ' + el.dataset.unit : ''), 'value');
    } else {
      hide(el);
    }
  });
  const isActive = el => el.getAttribute('aria-pressed') === 'true' || el.getAttribute('aria-selected') === 'true'
    || el.getAttribute('aria-current') || /\b(active|selected|current|on|is-active)\b/.test(el.className || '');
  doc.querySelectorAll('button, [role="tab"], [role="button"], a.btn, a.button').forEach(el => {
    if (kept(el) || !el.isConnected || !visible(el)) return;
    const text = (el.textContent || '').trim();
    isActive(el) && text ? swap(el, text, 'active') : hide(el);
  });
  doc.querySelectorAll('textarea').forEach(el => { if (!kept(el) && visible(el)) (el.value ? swap(el, el.value, 'value') : hide(el)); });
  if (badge) {
    const b = doc.createElement('div');
    b.id = 'artifact-preview-badge';
    b.textContent = 'Static preview · interactive version attached';
    doc.body.appendChild(b);
  }
  return n;
}

(async () => {
  if (!PW) throw new Error('playwright-core not found (set ARTIFACT_PLAYWRIGHT or npm install it into ~/agents/src/artifacts)');
  const { chromium } = require(PW);
  const [file, out, selector, waitArg] = process.argv.slice(2);
  const wait = Math.max(0, parseInt(waitArg || '800', 10) || 0);
  const browser = await chromium.launch({ executablePath: CHROME, headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--hide-scrollbars'] });
  const errors = [];
  let preview = null;
  try {
    const ctx = await browser.newContext({ viewport: { width: 1200, height: 800 },
      deviceScaleFactor: 2, colorScheme: 'dark', reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    page.on('pageerror', e => errors.push(String(e.message || e)));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('requestfailed', r => errors.push(`failed to load ${r.url()} (${(r.failure() || {}).errorText || 'error'})`));
    await page.goto('file://' + path.resolve(file), { waitUntil: 'load', timeout: 30000 });
    // Let CDN scripts / charts settle, but never hang on long-polling pages.
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    if (wait) await page.waitForTimeout(wait);
    if (process.env.ARTIFACT_KEEP_CONTROLS !== '1') {
      preview = await page.evaluate(staticPreview, process.env.ARTIFACT_BADGE === '1');
      await page.waitForTimeout(150);  // let charts reflow after controls changed size
    }
    if (selector) {
      const el = page.locator(selector).first();
      await el.waitFor({ state: 'visible', timeout: 10000 });
      await el.screenshot({ path: out, animations: 'disabled' });
    } else {
      await page.screenshot({ path: out, animations: 'disabled' });
    }
    console.log(JSON.stringify({ ok: true, errors: errors.slice(0, 5), preview }));
  } finally {
    await browser.close();
  }
})().catch(e => { console.log(JSON.stringify({ ok: false, error: String(e.message || e).split('\n').slice(0, 3).join(' | ') })); process.exit(1); });
