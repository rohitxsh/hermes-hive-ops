---
name: privacy-india-dpdp
description: Use when designing, reviewing or documenting how an app for users in India collects, uses, stores, shares or deletes personal data (privacy notice, consent, retention, deletion, breach handling, Aadhaar or ID documents, children), or when filling store privacy forms. An engineering checklist for India's Digital Personal Data Protection Act, not legal advice.
version: 0.1.0
author: Rohit Shrivastava (rohitxsh), Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [privacy, dpdp, india, compliance, consent, retention, security]
    related_skills: [app-store-release, crash-reporting, security-audit]
---

# Privacy for India (DPDP Act)

India's Digital Personal Data Protection Act, 2023 and the DPDP Rules, 2025 apply to digital personal data of people
in India. The Rules phase obligations in over time: check which provisions are in force today and record it, but
build to the full set, since launch data will be covered. This is an engineering checklist, **not legal advice**:
decisions that need a lawyer (what counts as a legitimate use, retention periods, Aadhaar handling, cross-border
transfers) go to the company's owners and counsel with the facts laid out.

## 1. Map the data first

For every screen, API, table, log, analytics or crash event and third-party SDK, record: the personal data items,
the purpose, the legal basis (consent, or a listed legitimate use), who can read it, where it is stored (region,
provider), how long it is kept and how it is deleted. Keep the map in the repo; every feature PR that touches
personal data updates it.

## 2. Checklist

- **Notice** before or at collection: an itemised list of the data and why, how to withdraw consent, how to use the
  rights below, and how to complain to the Data Protection Board. Plain language; English plus the user's language
  where the app supports it.
- **Consent**: free, specific, informed and an affirmative act (no pre-ticked boxes, no bundling with unrelated
  purposes). Withdrawing must be as easy as giving it, and stops the processing.
- **Minimise and limit**: collect only what the purpose needs; don't reuse data for a new purpose without a basis.
- **Rights**: access, correction, erasure and grievance redressal with a named contact and a response time; a way to
  nominate someone. Account deletion must really erase or anonymise data, except what the law requires keeping.
- **Retention**: delete when the purpose is served or consent is withdrawn; document any legal hold. Logs needed for
  security are kept for the required period and no longer.
- **Security safeguards**: encryption in transit and at rest, access control (RLS and least privilege), masking in
  logs, monitoring, backups, and processor contracts that bind vendors to the same rules.
- **Breach**: a written plan to inform the Data Protection Board and each affected person without delay, with the
  details the Rules require; CERT-In's cyber-incident reporting rules apply alongside (short reporting window).
- **Children** (under 18): verifiable parental consent; no tracking, behavioural monitoring or targeted ads aimed at
  children. If the service isn't meant for children, say so and check age at sign-up.
- **Identity documents and Aadhaar**: don't store full Aadhaar numbers or copies unless the law clearly allows it;
  prefer verification that returns a yes/no or a masked number; mask the first 8 digits wherever shown; restrict and
  log access to ID images; set a short, documented retention. Get explicit sign-off from the owners.
- **Third parties**: list every SDK and service that receives personal data (crash reporting, analytics, email/SMS,
  maps, payments) with what it gets; match the store privacy forms and the notice to this list.

## 3. Output

A short privacy review per feature (data map delta, checklist results, open questions for the owners) and, before
launch, a consolidated notice draft and data map for the owners and their counsel to approve.
