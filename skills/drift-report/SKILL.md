---
name: drift-report
description: >-
  Compare a project's design documents (architecture contracts, specs, READMEs) with the current code and report only
  where they diverge: missing features, missing fields, hardcoded values where logic was designed, different patterns
  or libraries than proposed, and code no document covers. Use for the scheduled weekly drift check or when asked to
  "check drift" / "do the docs still match the code".
license: Apache-2.0
metadata:
  adapted_from: "google/elephant-goldfish-model egm-drift-report (Apache-2.0)"
---

# Drift report: design documents vs code

1. **Inputs.** The repo and the document folders to check (usually `docs/architecture/` and `docs/specs/`, plus
   component READMEs). Never switch, edit, commit or push in the team's checkout: other agents work in it. Check the
   default branch in a temporary detached worktree and remove it afterwards:
   `git -C <repo> fetch -q origin && git -C <repo> worktree add --detach /tmp/drift-<repo> origin/main` …
   `git -C <repo> worktree remove --force /tmp/drift-<repo>`.
2. **For each document, one at a time** (so tool output stays small):
   - Read it. Note its intent and every concrete name it mentions: files, classes, functions, tables and fields,
     endpoints, config keys, libraries.
   - Find the matching code (paths in the doc, otherwise search for the names). If you had to search, note that the
     doc should link the file directly.
   - Read the current code, not your memory of it.
   - Report only differences:
     - **Missing feature:** described, not implemented.
     - **Incomplete model:** a class, table, struct or schema missing fields the doc specifies.
     - **Logic shortcut:** hardcoded values where dynamic logic was designed.
     - **Architectural divergence:** different pattern, library or flow than the doc proposes.
     - **Undocumented code:** significant logic no document or README covers.
   - Mark each 🔴 (behaviour or security differs from the contract), 🟡 (the doc is wrong or incomplete about real
     behaviour) or 🟢 (cosmetic, naming, links).
3. **Write** `<YYYY-MM-DD>_DRIFT_REPORT.md` in the project's private notes folder (for example
   `~/work/<project>/docs/drift/`), never in the repo or on GitHub:

   ```markdown
   # Drift report <date>: <repo> at <commit>
   ## <document name>
   - 🔴 <what differs> (doc: §/line; code: path:line)
   (or "No drift detected.")
   ```
4. **Act on it.** No drift: one line in your channel. Drift found: a short summary in your channel, and a Kanban card
   for whoever owns the fix: the doc owner (architect) when the doc is out of date, dev when the code misses the
   contract. Don't fix anything yourself during the check.
