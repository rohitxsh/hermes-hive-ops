---
name: mobile-e2e-maestro
description: Use to test a real Android app build end to end (installed APK, sign-up/login and other user journeys) on the VM's headless emulator with Maestro flows, and to collect screenshots and JUnit results as QA evidence.
version: 0.1.0
author: Rohit Shrivastava (rohitxsh), Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [android, e2e, maestro, emulator, qa, flutter, mobile]
    related_skills: [accessibility-review, flutter-add-integration-test, app-store-release]
---

# Mobile end-to-end tests (Maestro)

Tools on this VM: `android-emulator up|down|status` (a headless Android 14 phone, AVD `agents_api34`), `adb`, and
`maestro` (open source). The emulator is shared: check `android-emulator status` first, run one suite at a time,
and always `android-emulator down` when you finish, even after a failure.

## 1. Write flows in the repo

Keep flows in `.maestro/` next to the app, one journey per file, plus small sub-flows for repeated steps:

```yaml
appId: com.example.app            # the build's applicationId
env:
  EMAIL: ${EMAIL}
---
- launchApp: { clearState: true }
- tapOn: { id: "signin_email" }
- inputText: ${EMAIL}
- tapOn: "Send code"
- runFlow: subflows/enter-otp.yaml
- assertVisible: "Choose your mode"
- takeScreenshot: after-login
```

- Select by stable ids. In Flutter, give important widgets `Semantics(identifier: 'signin_email', ...)` (or a
  `Key` the app maps to it) so Maestro and screen readers both find them; this overlaps with accessibility work.
- Email codes: use the local stack's test mailbox or a dedicated test account; fetch the code with Maestro's
  `runScript` (JavaScript with `http.get`) from the mailbox API. Never use a real person's account or inbox.
- Cover the acceptance criteria literally: the happy path, a wrong code, an expired code, sign-out, and restart with
  the session restored (`stopApp` then `launchApp` without `clearState`).

## 2. Run

```bash
android-emulator up                                   # boots in about 1-3 minutes
adb install -r path/to/app.apk                        # the exact build under test
EMAIL=qa+run1@example.test maestro test .maestro/ --format junit --output maestro-report.xml
android-emulator down
```

Point the app at the local stack or the dev environment only, never production. If the emulator doesn't boot,
read the log path it prints and report it; don't retry in a loop.

## 3. Evidence

Attach the JUnit report, the screenshots (`~/.maestro/tests/<run>/` or `takeScreenshot` names) and the exact APK
name/commit to the QA comment. A flow that only passes on retry is a finding (flaky), not a pass.
