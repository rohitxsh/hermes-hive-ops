---
name: pr-body
description: >-
  Write a short pull request description a human reviewer can take in at a glance: a small visual of what changed,
  before/after evidence, and the merge danger (one-way or two-way door, blast radius). Use whenever you open a PR or
  rewrite its description, and when updating it after review changes.
license: MIT (adapted from mattpocock/skills `pr`, which credits humanlayer's show-me skill; see LICENSE)
---

# PR description

The reviewer is a person with a few minutes. Lead with what changes and how we know it works; leave the long story to
the issue. Skip preambles, keep prose to short lines, use the project's own words for things (the issue, PRD and
glossary), and follow your SOUL's GitHub privacy rules (no internal card IDs, board names or VM paths).

```markdown
Closes #<issue>

## Summary
<one or two plain sentences: what users or callers can now do, or what is fixed>

<one small visual, see below>

## Evidence
- **Before:** <screenshot, failing test, error output>
- **After:** <screenshot, the same test passing, output>

## Merge danger
**Door:** one-way | two-way <one line on why>
**Blast radius:** <one word or short phrase> <one line: who or what could break>
```

## Summary visual

Pick the smallest view that makes the key point; usually one, rarely more than two. Keep only the calls, files,
widgets, tables and states needed to see the change, and put the visual right after the sentence it supports.

- Logic: short pseudocode.
- Runtime flow: a call tree.
- UI: a widget tree with the state that matters.
- Files or a broad refactor: a shallow file tree.
- Interactions or data flow: a small Mermaid sequence diagram.
- What changes inside an existing shape: a `diff` of that shape (tree, call tree or flow), not of the code.

```diff
 RideDetailsScreen
   RideSummaryCard
+  SeatPicker            # new: choose 1–3 seats
   BookButton
-    onTap: book(1)
+    onTap: book(selectedSeats)
```

## Evidence

Screenshots or a short screen recording are best for visible changes (web build or emulator). Otherwise show the
exact test that failed before and passes now, or the command output. Link the CI run. No evidence yet means the PR
stays draft.

## Merge danger

- **Two-way door:** easy to walk back by reverting (UI, copy, isolated logic behind a flag).
- **One-way door:** hard or impossible to undo: data migrations that drop or rewrite data, RLS or permission changes
  already in use, published app builds, emails or messages sent, external accounts or billing. Say what makes it
  one-way and what was done to make it safe (backup, expand–contract migration, feature flag).
- **Blast radius:** what could break if it's wrong: one screen, all signed-in users, every rider's bookings, CI for
  everyone. Name it honestly; a small radius is a reason to merge, not something to hide.

## When things change

After review fixes, update Summary and Evidence to the final state instead of appending a changelog; the commit list
already has the history.
