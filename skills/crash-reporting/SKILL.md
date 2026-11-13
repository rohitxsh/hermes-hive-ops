---
name: crash-reporting
description: Use when adding or reviewing crash and error reporting for a Flutter app or website (Sentry SDK, or self-hosted GlitchTip which speaks the same protocol), including privacy scrubbing, release tagging, symbol upload and alert routing.
version: 0.1.0
author: Rohit Shrivastava (rohitxsh), Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [crash-reporting, sentry, glitchtip, observability, flutter, monitoring, privacy]
    related_skills: [privacy-india-dpdp, app-store-release]
---

# Crash and error reporting

Choosing the service is the owners' decision (where the data lives, cost, who has access): **Sentry** (hosted, has a
free developer tier) or **GlitchTip** (open source, self-hosted, works with the same Sentry SDKs). Prepare the
comparison and the privacy impact; set it up only after they choose.

## 1. Flutter setup (Sentry SDK)

- Add `sentry_flutter`; wrap start-up in `SentryFlutter.init` with the DSN from the build configuration
  (`--dart-define`), never hard-coded, and different per environment.
- Set `environment` (dev/beta/production), `release` (`<app>@<version>+<build>`) and a low `tracesSampleRate`
  (for example 0.1, or 0 until performance data is wanted).
- **Privacy first**: `sendDefaultPii = false`; a `beforeSend` that removes emails, phone numbers, tokens, codes,
  ID numbers and free-text fields; no screenshots or view hierarchy on screens that show personal data; user
  identity only as an internal random id. Crash data still counts as personal data: list the service in the
  privacy notice and the store privacy forms.
- Release builds: upload debug symbols / obfuscation maps (`sentry_dart_plugin`) in CI so stack traces are
  readable; for Flutter web, upload source maps. Keep the auth token in CI secrets only.

## 2. Website

Use the browser SDK (or the framework's SDK) with the same environment/release scheme, the same scrubbing, and
source maps uploaded at build time.

## 3. Prove it works

In a dev build, trigger a test error and a test crash, then confirm: the event arrives with the right environment
and release, the stack trace is readable, and none of the scrubbed fields appear. Record this in the setup PR.

## 4. Alerts and triage

Route new-issue and regression alerts to the team channel (not every event). Each new crash group gets a card or
issue with frequency, affected versions and the owner; a fixed crash links the fix PR and is marked resolved in
that release, so a regression reopens it.
