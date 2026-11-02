---
name: goldfish-review
description: >-
  Zero-context review of a design document before work starts: fresh read-only subagents (comprehension, design
  critic, implementation readiness) read only the document and the files it cites, so unstated assumptions and gaps
  show up. Use for the contract of a major feature or a high-risk area before handing it to dev, for a major PRD before
  the team approves it (comprehension only), or when asked to "goldfish review" a doc. Not for small or obvious changes.
license: Apache-2.0
metadata:
  adapted_from: "google/elephant-goldfish-model (Apache-2.0): reviewer personas, synthesis and resolve rules"
---

# Goldfish review

You wrote (or own) the document: you are the **elephant**, with all the context. Reviewers are **goldfish**: fresh
subagents that see only the document and the files it links to. A gap a goldfish finds is a gap a new teammate, or
the agent who implements it, would hit too. A review complements tests, QA and human judgment; it replaces none of them.

## When to run it
- **Contract of a major feature or a high-risk area** (auth, security, payments, location data, migrations or data
  deletion, anything that deploys or costs money), before handing it to dev: all three lenses.
- **PRD of a major feature**, before asking the team to approve it: the **comprehension** lens only.
- Skip it for small, clear changes and bug fixes. Each lens is one model run.

## 1. Launch the reviewers (one `delegate_task` call, tasks in parallel)
Give every task the same `context`: the absolute path of the document, the line range or "full file", and the paths
of files it cites (specs, code, contracts). Nothing else: no summary, no conversation, no intent. Each task's `goal` is
the lens text below, verbatim, followed by: "Read-only: do not write, edit, run builds or change anything. Report in
plain language. Mode: REVIEW. Target: <path> (<range>)."

**Comprehension** (naive reader). "You are a fresh reader who just joined the project; you know software, not this
project. First paraphrase, under two headings, **What this proposes** and **How the existing system works, per this
document** (2-5 sentences each). If you cannot paraphrase a section, that section is a Blocker. Then flag terms,
systems or concepts specific to this project that are neither defined in the document nor linked; workflows that
assume unstated setup; vague explanations ('the system handles this'). Do not flag general engineering terms. For each
finding: Severity (Blocker | Major | Nit), Affected scope (section or lines), Description and rationale."

**Design critic** (skeptical senior engineer). "Stress-test the design: unbacked assumptions about external systems,
data or performance; failure modes, scaling bottlenecks, single points of failure, security and privacy risks the
design introduces but does not mitigate; missing answers a design of this kind must give (goals, non-goals,
alternatives, risks, rollout and rollback, how success is measured). For each finding: Severity (Blocker | Major |
Nit), Affected scope, Finding and recommendation."

**Implementation readiness** (the engineer who will build it). "Ask: do I know exactly what to code, where and how,
from this text alone? Flag every place that leaves a design decision to the implementer (a data type, an API
signature, an error-handling strategy, a library choice), high-level steps where precise ones are needed ('update the
auth service' instead of 'add field X to Y in file Z'), and missing schemas, migration steps or test assertions. For
each finding: Severity (Blocker | Major | Nit), Affected scope, Finding and guidance."

**Fail closed.** A reviewer that errors, times out or returns no report did not review: retry it once; if it fails
again mark it `not run`, never "no findings". If no fresh subagent can be started, stop and say so: a review in your
own context is not a goldfish review.

## 2. Synthesize the report
Merge all findings, remove duplicates, normalize scopes, group them 🔴 Blocker → 🟡 Major → 🟢 Nit, and write
`goldfish-review-<doc-name>-<YYYY-MM-DD>.md` in the project's private notes folder (for example `~/work/<project>/docs/reviews/`),
never in the code repo or on GitHub:

```markdown
# Goldfish review: <document> (<range>)
## Reviewer status
| Reviewer | Status |
| comprehension | completed / not run |
## Paraphrase (comprehension)
What this proposes: ... / How the existing system works, per this document: ...
## Findings
### <short name>: 🔴 Blocker
- Lens: design critic · Scope: §5 / lines 120-140
- Gap: ...
- Recommendation: ...
## Resolution (filled in step 3)
| Finding | Decision | Change or evidence |
```

## 3. Resolve each finding (you, with your context)
Give each finding exactly one decision:
- **PROPOSE FIX**: valid; change the document precisely.
- **CONTEST**: wrong, and you can cite evidence the reviewer could have read (a file and symbol, or a decision
  already recorded in the document). "It was intentional" is not evidence.
- **ESCALATE**: wrong, but the evidence lives outside anything the reviewer could read (a team convention, a verbal
  decision): don't change the doc for it; raise it with the owner.
- **DECLINE**: a Nit you choose not to fix; record it.

Rules: do not contest a comprehension gap (if a fresh reader could not follow it, the document lacks context); do not
change a severity (contest it with a reason instead); add context because a human reader needs it, not only to
satisfy a reviewer. Fill the Resolution table: it is the traceability from finding to change.

## 4. One re-audit, then stop
After fixing, re-run only the lenses that had 🔴 or 🟡 findings, once, on the changed sections. Whatever is still open
after that goes into an **Accepted trade-offs** section of the document (what, why, who accepted it) or becomes one
precise question for the owner. Never start a third round on the same findings.

## 5. Hand off
Attach the report to the Kanban card (or link it), and put a one-line summary in the handoff: "Goldfish review: 3/3
lenses, 0 🔴, 2 🟡 fixed, 1 🟢 declined". For a PRD checkpoint, include the paraphrase and any open 🔴 in the approval
question so the humans see whether the PRD reads the way it was meant.
