---
name: app-store-release
description: Use when preparing, submitting or reviewing a Google Play or Apple App Store release (testing tracks, store listing, Data safety form, App Privacy labels, review notes, signing, staged rollout) or when a store review rejects a build.
version: 0.1.0
author: Rohit Shrivastava (rohitxsh), Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [android, ios, google-play, app-store, testflight, release, mobile]
    related_skills: [privacy-india-dpdp, accessibility-review, crash-reporting, mobile-e2e-maestro]
---

# App store release

Store rules change often: check the current Play Console policy pages and Apple's App Review Guidelines before you
rely on a number or date below, and record what you checked. Submitting, publishing or changing a store account is a
person's decision: prepare everything, then ask once with the exact build and checklist.

## 1. Before any store work

- The company owns the developer accounts (Play Console organisation account; Apple Developer Program for an
  organisation, which needs a D-U-N-S number). Never use a personal account for the company app.
- Signing: Android uploads an App Bundle (`.aab`) signed with the upload key, and Play App Signing holds the app
  signing key; iOS needs a distribution certificate and an App Store provisioning profile. Keys and their backups
  are owned by a named person; never generate a replacement key without them.
- Version: bump `versionName`/`versionCode` (Android) and `CFBundleShortVersionString`/`CFBundleVersion` (iOS) from
  the release record, never by hand on a branch.

## 2. Google Play checklist

- Target SDK meets Play's current target-API requirement (it rises every year; check it in the Console).
- Testing tracks: internal → closed → production. A personal developer account created recently must run a closed
  test with enough testers for the required days before production; an organisation account usually is not bound
  by that, but confirm in the Console.
- App content: privacy policy URL (public, matches the app), **Data safety** form (every data type collected or
  shared, why, whether optional, encrypted in transit, deletion available), ads declaration, content rating,
  target audience, and declarations for sensitive permissions (background location, foreground service types).
- **Account deletion**: an app that lets people create accounts must offer deletion in the app and a web link to
  request it, and the Data safety form must say so.
- Store listing: name (≤30 characters), short description (≤80), full description (≤4000), 512×512 icon, 1024×500
  feature graphic, phone screenshots of the real app. No claims the app doesn't meet.
- Release: start with a staged rollout (for example 5% → 20% → 50% → 100%), watch crash and ANR rates between
  steps, and halt the rollout if they jump.

## 3. Apple App Store checklist

- App Store Connect record, bundle ID, TestFlight: internal testers first, external testers after Beta App Review.
- **App Privacy** labels must match what the app and every SDK actually collect; privacy policy URL required.
- Account deletion inside the app is required when the app supports account creation.
- Sign-in: if the app offers a third-party or social login, the review guidelines require an equivalent
  privacy-friendly login option; email one-time codes alone don't trigger that.
- **Review notes**: reviewers must be able to sign in. With email one-time codes, give a working review account
  and a way to receive its code (a monitored mailbox or a documented review-only code), plus any steps to reach
  the main features.
- Encryption: if the app only uses standard HTTPS/TLS, set `ITSAppUsesNonExemptEncryption` to `false`.
- Purpose strings for every permission (location, camera, photos, notifications) in plain words.
- Screenshots for the required iPhone sizes, 1024×1024 icon without transparency. Use phased release for updates.

## 4. Release evidence

Keep one release checklist per version in the repo (build number, commit, store forms completed, screenshots,
reviewer notes, rollout plan, who approved). Link the QA and accessibility results. When a review rejects the
build, quote the exact guideline and message, fix only that, and reply in the resolution centre.
