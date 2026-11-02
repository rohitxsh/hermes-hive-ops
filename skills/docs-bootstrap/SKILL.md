---
name: docs-bootstrap
description: >-
  Write contract-style READMEs for an existing codebase that has no design docs, so people, reviewers and drift checks
  have something accurate to work from: one root "blueprint" plus one README per significant component, describing
  overview, interface, invariants, side effects and how to verify. Documentation only. Use once per repo or when asked
  to "bootstrap docs" / "document this codebase".
license: Apache-2.0
metadata:
  adapted_from: "google/elephant-goldfish-model egm-bootstrap and its README templates (Apache-2.0)"
---

# Bootstrap documentation for an existing codebase

**Constraints.** Documentation only: never change code, configs or tests; never commit or push (leave the new files
for the normal review and PR flow, or for the owner). Describe what the code does today, not what it should do.

1. **Map the repo** level by level (`find`, `git ls-files`): languages, build and test commands, top-level components.
   If it has more than about 15 components worth a README, list them and ask the owner which to cover first.
2. **Skip what is already documented**: an existing accurate README or design doc is kept; only fill gaps.
3. **Work bottom-up.** For each component directory, read the code (in parallel with `delegate_task` for large repos:
   one read-only subagent per component, each returning the filled template), then write `README.md` there:

   ```markdown
   # <Component>
   ## Overview
   <its role and goals, in prose>
   ## Interface
   - <public classes, functions, endpoints, commands>
   - <sub-components with relative links to their READMEs>
   ## Invariants
   - <state and call rules that must keep holding>
   ## Side effects
   - <state changes, network calls, disk, locks, external services>
   ## Verification
   - Run: `<test command>`
   ```
4. **Write the root blueprint** (`README.md` at the repo root, or `docs/architecture/overview.md` if the root README
   is a user-facing one): system overview, subdirectories and boundaries (with links), global invariants, shared
   resources and integrations, how to run the whole test suite.
5. **Verify** every link resolves to an existing file and every command exists in the repo. Then run the
   `drift-report` skill once against the new docs: they should report no drift.
