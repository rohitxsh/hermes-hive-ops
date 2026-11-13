---
name: presentations
description: Use when asked for a presentation, slides, a deck or a .pptx (pitch, status update, review, demo, training). Plans the story, builds the deck with python-pptx (microsoft-office skill) or Marp, renders every slide to an image and checks it before delivering .pptx plus .pdf.
version: 0.1.0
author: Rohit Shrivastava (rohitxsh), Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [presentation, slides, deck, pptx, powerpoint, marp, pdf]
    related_skills: [microsoft-office, pdf, interactive-visuals]
---

# Presentations

Free, open-source tools on this machine: **python-pptx** (through the `microsoft-office` skill's shared documents
environment), **Marp CLI** (`marp`, Markdown to PPTX/PDF/HTML), **LibreOffice** headless (`soffice`, PPTX to PDF)
and **poppler** (`pdftoppm`, PDF pages to PNG). Nothing needs installing or a paid service.

## 1. Plan before building

- Ask (once, only if it isn't clear) who the audience is, the one decision or takeaway, the length and any brand
  template. Otherwise pick sensible defaults and say what you assumed.
- Write the outline first: title, the problem or context, 3–6 main points (one slide each, or two for a dense one),
  evidence (numbers, a chart, a screenshot), next steps or the ask, and a closing slide. Put the takeaway in each
  slide's title as a full sentence ("Sign-ups doubled after the OTP fix"), not a label ("Results").
- Use only real facts and figures from the conversation, the repo or files you were given; mark anything assumed.

## 2. Pick the tool

| Need | Use |
|---|---|
| An editable deck people will reuse, a company template, charts, speaker notes | `microsoft-office` skill: `pptx_create.py` from a JSON spec, or python-pptx directly (`references/powerpoint.md` there) |
| A quick text-and-image deck, code or diagrams, or a deck kept next to docs in git | Marp: a `.md` file with `marp: true`, then `marp --no-stdin --pptx deck.md -o deck.pptx` (and `--pdf`) |
| A brand `.pptx` template was supplied | python-pptx on that template's layouts (keep its masters, fonts and colours) |

Marp exports PPTX slides as images, so text in that PPTX isn't editable; when people must edit it, use python-pptx.

## 3. Design rules

- One idea per slide; at most 5–6 bullets of a few words each; no paragraphs (put detail in the speaker notes).
- Body text 20 pt or larger, titles 32 pt or larger; one or two fonts; high contrast; consistent margins and
  alignment; the same position for titles on every slide.
- Prefer a chart, diagram or image over a table; label axes and units; highlight the one number that matters.
- A visual hierarchy per slide: one focal element. Leave white space; don't fill every corner.
- Add speaker notes with what to say on each slide when someone will present it.
- Keep 16:9 unless told otherwise. Use the team's colours or logo when given; never invent a logo.

## 4. Render and look at every slide (required)

```bash
soffice --headless --convert-to pdf deck.pptx            # writes deck.pdf next to it
pdftoppm -png -r 60 deck.pdf slide                         # slide-1.png, slide-2.png, ...
```

Open each PNG and check: text cut off or overflowing its box, overlapping shapes, unreadable contrast, tiny text,
empty placeholders, wrong slide order, broken characters (non-Latin scripts need a font that has them; the Noto
fonts are installed). Fix and re-render until every slide is clean. Say what you checked.

## 5. Deliver

- Send the `.pptx` and the `.pdf` (the PDF previews anywhere) as files, for example with `discord-send --file`,
  plus a three-line summary: audience, takeaway, slide count. Keep the source (`deck.json` or `deck.md`) with the
  project files so the deck can be updated later.
- Don't publish a deck outside the team or put private data in it without the owner's yes.
