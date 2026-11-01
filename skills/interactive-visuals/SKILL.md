---
name: interactive-visuals
description: "Use when comparing multi-variable data, showing trends, explaining architecture/flows, building calculators/simulators or prototyping UI. Build one self-contained dark HTML file, run publish-artifact, paste the printed paths as plain text: Discord shows the PNG inline and attaches the interactive HTML."
version: 1.2.0
metadata:
  hermes:
    tags: [visualization, html, artifacts, charts, diagrams, discord]
---

# Interactive visuals

## When to use
Make a visual, without being asked, when the answer involves:
- comparing data across several variables (options, plans, prices, benchmarks);
- trends or charts over time or categories;
- system, architecture, data or process flows;
- calculators, simulators, what-if models (loan, budget, capacity, pricing);
- UI prototypes or mockups.

Skip it for simple Q&A, short factual answers, or anything a sentence or short list answers.

Two kinds of output:
- **Interactive** (default for the cases above): PNG preview inline plus the HTML file to open in a browser.
- **Static chart** (one chart, nothing to explore): the same HTML, published with `--png-only`, so only the image is sent.

## How to build
Write ONE standalone HTML5 file at `~/.hermes/cache/scratch/<descriptive-name>.html`. Start from `templates/base.html` in this skill when it fits (dark theme, Chart.js, two sliders).
- **Self-contained:** inline CSS, JS and data (put data in a `<script>` as JSON). No local relative assets (`./data.json`, `img/x.png`): they are not copied. CDN libraries are fine; use these pinned versions:
  - Chart.js `https://cdn.jsdelivr.net/npm/chart.js@4.6.1/dist/chart.umd.min.js`
  - Plotly.js `https://cdn.plot.ly/plotly-2.35.2.min.js`
  - Mermaid `https://cdn.jsdelivr.net/npm/mermaid@11.17.2/dist/mermaid.min.js`
  - Tailwind `https://cdn.tailwindcss.com/3.4.16`
  - Alpine `https://cdn.jsdelivr.net/npm/alpinejs@3.14.9/dist/cdn.min.js`, or React + ReactDOM UMD from unpkg (plain `React.createElement`).
- **Dark theme:** background `#0f172a`, text `#e2e8f0`, panels `#1e293b`, borders `#334155`, accent `#38bdf8`; set `color-scheme: dark`. Style chart axes, gridlines and legends for dark (Chart.js: `Chart.defaults.color`, `borderColor`; Plotly: `template: 'plotly_dark'`, `paper_bgcolor`/`plot_bgcolor`; Mermaid: `theme: 'dark'`).
- **Fits the preview:** `<meta name="viewport" content="width=device-width, initial-scale=1">`, fluid widths, charts with `maintainAspectRatio: false` in sized containers. The PNG is the first 1200x800 of the page, so put the title, takeaway and main chart above the fold. For one element only, use `--selector`.
- **Interactive:** add at least one real control that fits the data: tooltips, filters/toggles, sliders, tabs, sortable tables, step-through for flows. Static charts need none. For panels toggled with the HTML `hidden` attribute, include `[hidden] { display: none !important; }`; explicit grid/flex display styles can otherwise override the browser's hidden styling and expose inactive panels.
- **The PNG is a static image:** Discord can't click it. `publish-artifact` therefore shows controls as their current state: sliders, dropdowns and inputs become their values ("Surge cap 2 ×"), the active button or tab becomes a plain label, other buttons and tabs disappear, `<details>` open, chart toolbars hide, and a small "Static preview · interactive version attached" badge appears. Design for it:
  - Choose the default state that tells the story best: it is what the image shows.
  - Mark hints that only make sense when clicking ("click a bar…", "hover for details") and purely interactive bits with `data-interactive-only`; they are hidden in the image. For a slider, put the unit in `data-unit` (`<input type="range" data-unit="%">`).
  - For tabs, the image shows only the active panel. If every panel matters, add a static summary for the preview: style it with `html[data-preview="png"]` selectors, or listen for the `artifact-preview` event, which fires before the screenshot.
  - UI prototypes and mockups, where the buttons and inputs are the design: publish with `--keep-controls` so they stay visible.
  - Wrap anything that must keep its interactive look in the image in `data-keep-in-preview`.
- **Readable on its own:** title, one-line takeaway, units, labels and a source line. Use real numbers from your tools; never invent data to fill a chart.
- **Private by default:** the HTML is posted to the Discord channel. Leave out secrets, credentials and private details you would not show on screen.
- Keep the file small (well under 8 MB, Discord's upload limit is 10 MB): no embedded images or huge data dumps.

## How to deliver to Discord
1. Run `publish-artifact ~/.hermes/cache/scratch/<name>.html`. Options: `--png-only` for a static chart, `--keep-controls` for UI prototypes and mockups, `--selector '<css>'` to shoot one element, `--wait <ms>` for slow or animated pages, `--slug <name>`.
2. If it fails, nothing is published: read the error, fix the page or the selector, and rerun. If it prints "Warning: the page logged errors", look at the PNG (vision) and fix the page if it looks wrong (a failed CDN load leaves a blank area).
3. Verify the published copy before delivery: inspect the PNG for clipping/overlap at the preview viewport, then open the HTML in a browser and exercise each control while checking for JavaScript errors. For tabs, assert that only the initial panel is visible, click another tab and check both panels' visibility, then return to the initial tab. A screenshot alone does not test interaction. After any fix, republish and verify the new copy rather than an older timestamped artifact.
4. Paste the lines it prints between the `-----` markers into your reply as **plain text, never inside backticks or a code block**:
   - `~/.hermes/cache/scratch/<slug>.png`: the gateway embeds the image inline;
   - `~/.hermes/cache/scratch/<slug>.html`: the gateway attaches the interactive file;
   - a LAN link, only on VMs that serve one (vm-a: WebUI login, home LAN only). Include it as printed so it stays clickable.
5. For interactive output, say in one line that the image is a static preview and that the attached HTML file is the interactive version (download it and open it in a browser; Discord doesn't run it inline), or give the link where there is one.

## Troubleshooting
- "screenshot failed ... error while loading shared libraries": Chromium is missing system libraries on this VM. Send the text answer without the visual and run `report-issue` with the error.
- "playwright-core not found" or "node not found": the renderer isn't installed here; report it the same way.
- `publish-artifact --selftest` checks the whole pipeline in a few seconds.

## Notes
- Permanent copies live in `~/artifacts/<timestamp>-<slug>.html`; scratch files are pruned after 24 h idle. To resend an old one, rerun `publish-artifact` on the `~/artifacts` file.
- The preview needs internet for the CDN libraries, and so does the HTML when it is opened.
- This skill lives in `~/agents/shared-skills/` and is shared by every profile (`skills.external_dirs`). Improve it there only when the change helps every profile.
