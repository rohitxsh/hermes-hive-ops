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
- **Static visual** (one chart or process diagram, nothing to explore): the same HTML, published with `--png-only`, so only the image is sent. Do not add controls merely to make a straightforward explanation interactive.

## Architecture and workflow diagrams
1. Ground the diagram in the current authoritative documentation or operating rules before drawing it; use session history for context, not as a substitute for newer policy.
2. Identify the main path, optional branches, feedback loops and decision gates. Distinguish role handoffs from ticket statuses and separate implementation review, QA, merge and release gates; collapsing them into one approval box can imply permissions that were never granted.
3. Label conceptual system maps and prescribed workflows as such. Do not present a model diagram as private reasoning, neural telemetry or a live execution trace; do not present a workflow explanation as an audit of current ticket state.
4. Choose the output by the reader's task: use a static diagram for an overview, or selectable nodes with one shared detail panel when the reader benefits from exploring each component. Keep the main path legible in the PNG without opening the HTML.

## UI mockups and existing brand artwork
1. Establish the deliverable before rendering: distinguish original source/reference screens, proposed updated mockups, and implemented UI. A request for updated screens needs actual revised visuals; source screenshots alone do not satisfy it.
2. Inventory supplied artwork before inserting a logo placeholder: search project asset folders and archives, then visually inspect the supplied brand guide and relevant screen PDFs. Record separately whether the logo exists, whether a standalone master is available, and whether the selected reproduction is suitable for production; a missing export does not make an existing logo pending.
3. Use the genuine supplied logo variant matched to the screen background. Preserve its proportions, colours and original effects as one piece. For review-only mockups, when the original artwork exists only inside a supplied document and reuse is permitted, reproduce that artwork faithfully by extraction or cropping; label its source and quality limits separately from production-master readiness. Do not redraw or typeset an imitation. If no usable artwork is found, state the bounded search result rather than asserting that the logo does not exist.
4. Apply corrections to the whole review set: standalone screens, contact sheets, optional HTML and archive. Remove superseded placeholder text and misleading asset disclosures, preserve the previous version, and regenerate hashes for the corrected version. Inspect the newly rendered logo at its displayed size, along with clipping and background compatibility; old-version checks do not cover new bytes.
5. Deliver screens directly in the conversation: start with small, readable contact-sheet groups and provide full-size images or a complete archive for detail. A ZIP is supplementary, not a substitute for requested inline screens. Mark proposals and source references accurately; report preparation, attachment emission, confirmed access and human approval as separate states.

## How to build
Write ONE standalone HTML5 file at `~/.hermes/cache/scratch/<descriptive-name>.html`. Start from `templates/base.html` in this skill when it fits (dark theme, Chart.js, two sliders).
- **Self-contained:** inline CSS, JS and data (put data in a `<script>` as JSON). No local relative assets (`./data.json`, `img/x.png`): they are not copied. CDN libraries are fine; use these pinned versions:
  - Chart.js `https://cdn.jsdelivr.net/npm/chart.js@4.6.1/dist/chart.umd.min.js`
  - Plotly.js `https://cdn.plot.ly/plotly-2.35.2.min.js`
  - Mermaid `https://cdn.jsdelivr.net/npm/mermaid@11.17.2/dist/mermaid.min.js`
  - Tailwind `https://cdn.tailwindcss.com/3.4.16`
  - Alpine `https://cdn.jsdelivr.net/npm/alpinejs@3.14.9/dist/cdn.min.js`, or React + ReactDOM UMD from unpkg (plain `React.createElement`).
- **Theme:** for generic charts and explanatory tools, use background `#0f172a`, text `#e2e8f0`, panels `#1e293b`, borders `#334155`, accent `#38bdf8`; set `color-scheme: dark`. For branded UI mockups, use the product's documented light/dark roles and genuine matching logo variants instead of imposing this generic palette. Style chart axes, gridlines and legends for dark (Chart.js: `Chart.defaults.color`, `borderColor`; Plotly: `template: 'plotly_dark'`, `paper_bgcolor`/`plot_bgcolor`; Mermaid: `theme: 'dark'`).
- **Fits the preview:** `<meta name="viewport" content="width=device-width, initial-scale=1">`, fluid widths, charts with `maintainAspectRatio: false` in sized containers. The PNG is the first 1200x800 of the page: budget for the title, diagram, detail panel, sources and any safety/interpretation caveat within that height. Keep bottom padding as a clipping margin. If the footer is cut off, reduce outer padding and section gaps before shrinking text; screenshot cropping can otherwise remove the qualification that makes the visual accurate. For one element only, use `--selector`.
- **Interactive:** add at least one real control that fits the data: tooltips, filters/toggles, sliders, tabs, sortable tables, step-through for flows. Static charts need none. For panels toggled with the HTML `hidden` attribute, include `[hidden] { display: none !important; }`; explicit grid/flex display styles can otherwise override the browser's hidden styling and expose inactive panels.
- **The PNG is a static image:** Discord can't click it. `publish-artifact` therefore shows controls as their current state: sliders, dropdowns and inputs become their values ("Surge cap 2 ×"), the active button or tab becomes a plain label, other buttons and tabs disappear, `<details>` open, chart toolbars hide, and a small "Static preview · interactive version attached" badge appears. Design for it:
  - Choose the default state that tells the story best: it is what the image shows.
  - Mark hints that only make sense when clicking ("click a bar…", "hover for details") and purely interactive bits with `data-interactive-only`; they are hidden in the image. For a slider, put the unit in `data-unit` (`<input type="range" data-unit="%">`).
  - For tabs, the image shows only the active panel. If every panel matters, add a static summary for the preview: style it with `html[data-preview="png"]` selectors, or listen for the `artifact-preview` event, which fires before the screenshot.
  - UI prototypes and mockups, where the buttons and inputs are the design: publish with `--keep-controls` so they stay visible.
  - Wrap anything that must keep its interactive look in the image in `data-keep-in-preview`.
  - Preserve essential clickable SVG diagrams by adding `data-keep-in-preview` to the enclosing SVG. Nodes with `role="button"` can otherwise disappear from the PNG during control stripping, leaving only arrows; inspect the rendered PNG, not just the live HTML.
- **Readable on its own:** title, one-line takeaway, units, labels and a source line. Use real numbers from your tools; never invent data to fill a chart.
- **Private by default:** the HTML is posted to the Discord channel. Leave out secrets, credentials and private details you would not show on screen.
- Keep the file small (well under 8 MB, Discord's upload limit is 10 MB): no huge data dumps, and no embedded images except, for self-contained branded mockups, the optimized genuine artwork they need to render faithfully. Check the final file size before delivery.

## How to deliver to Discord
1. Run `publish-artifact ~/.hermes/cache/scratch/<name>.html`. Options: `--png-only` for a static chart, `--keep-controls` for UI prototypes and mockups, `--selector '<css>'` to shoot one element, `--wait <ms>` for slow or animated pages, `--slug <name>`.
2. If it fails, nothing is published: read the error, fix the page or the selector, and rerun. If it prints "Warning: the page logged errors", look at the PNG (vision) and fix the page if it looks wrong (a failed CDN load leaves a blank area).
3. Verify the published copy before delivery: inspect the PNG for clipping/overlap through the final footer at the preview viewport. For interactive output, open the published HTML in a browser and exercise each control while checking for JavaScript errors. For selectable diagrams, activate every node and assert that its expected title/body appears with exactly one active selection; test keyboard activation and restore the intended default. For tabs, assert that only the initial panel is visible, click another tab and check both panels' visibility, then return to the initial tab. A screenshot alone does not test interaction. After any fix, republish and verify the new copy rather than an older timestamped artifact.
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
