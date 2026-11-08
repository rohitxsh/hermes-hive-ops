---
profiles: *
exclude: random default
---
- Size coding work before development starts (whoever writes or picks up a coding issue: PM, architect, dev, devops):
  - One issue per PR. Each issue has at most 10 numbered acceptance criteria; split it if it needs more.
  - A PR changes at most about 1,500 lines of product code (tests, fixtures, generated and lock files don't count). When the estimate is larger, split the issue before coding, not after.
  - Copying in or modifying a third-party library (vendoring, forks, patched SDKs) is its own PR and needs a person's yes first.
  - Architecture and design guarantees (timeouts, cancellation, recovery, internal invariants) live in the design doc. They are review criteria only when the issue lists them as numbered acceptance criteria.
- An open PR already over these limits is not restarted or force-split: finish it under the review-round rules, move what isn't needed for its acceptance criteria to "Part 2" cards, and size the next issues properly.
