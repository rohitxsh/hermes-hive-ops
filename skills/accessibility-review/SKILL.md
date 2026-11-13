---
name: accessibility-review
description: Use when building or reviewing screens of a Flutter app or a website for accessibility (screen readers, contrast, tap target size, text scaling, focus order, forms and one-time-code inputs), aiming at WCAG 2.2 AA, and to add automated accessibility checks to tests.
version: 0.1.0
author: Rohit Shrivastava (rohitxsh), Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [accessibility, a11y, wcag, flutter, web, semantics, qa]
    related_skills: [mobile-e2e-maestro, frontend-design, playwright-cli]
---

# Accessibility review

Target WCAG 2.2 level AA on the web and the equivalent platform guidance on Android and iOS. Every finding names the
screen, the element, the rule, the user impact and the fix, with a severity (blocks a task / hard / annoying).

## 1. Checklist (every new or changed screen)

- **Labels**: every interactive element and meaningful image has an accessible name; decorative images are hidden
  from screen readers. Icon-only buttons get a label ("Close", not "X").
- **Contrast**: text at least 4.5:1 (3:1 for large text), icons and control borders at least 3:1, in light and
  dark themes. Don't use colour alone to show state or errors.
- **Targets**: at least 48×48 dp on Android, 44×44 pt on iOS, 24×24 CSS px minimum on the web, with spacing.
- **Text scaling**: layout survives 200% text (no clipping, no overlap, scrolling where needed).
- **Order and focus**: reading and focus order follow the visual order; focus is visible on the web; dialogs trap
  and return focus; nothing is reachable only by gesture.
- **Forms**: visible labels (not only placeholders), errors announced and explained, the one-time-code field uses
  autofill (`autofillHints: [AutofillHints.oneTimeCode]` in Flutter, `autocomplete="one-time-code"` on the web).
- **Motion and time**: respect reduced-motion settings; no time limits without a way to extend.

## 2. Automated checks

- Flutter widget tests (built into `flutter_test`, no extra package):

  ```dart
  final handle = tester.ensureSemantics();
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  await expectLater(tester, meetsGuideline(textContrastGuideline));
  handle.dispose();
  ```

  Add a test that pumps key screens with `MediaQuery(data: ...copyWith(textScaler: TextScaler.linear(2.0)))` and
  asserts there are no overflow errors.
- Web: run axe-core in the browser tests (`npx @axe-core/cli <url>` for a quick scan, or `@axe-core/playwright` in
  Playwright tests) and the Lighthouse accessibility audit; fail the check on serious or critical violations.

## 3. Manual pass

Automation finds about a third of problems. For each core journey (sign-up, login, the main task, settings,
account deletion) do one pass with TalkBack on the emulator (`mobile-e2e-maestro` has the emulator) or a real
device, and one keyboard-only pass on the web. Record what you tested and what you couldn't.
