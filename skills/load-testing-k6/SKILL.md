---
name: load-testing-k6
description: Use to measure how an API or backend holds up under load, or to prove abuse protections work (rate limits, one-time-code pumping, brute force), with k6 against a local stack or an approved non-production environment.
version: 0.1.0
author: Rohit Shrivastava (rohitxsh), Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [performance, load-testing, k6, rate-limit, abuse, security, devops, qa]
    related_skills: [security-audit, supabase]
---

# Load and abuse testing (k6)

`k6` (open source, Grafana) is installed on this VM. Load tests can cost money, trip provider limits and send real
emails or SMS, so the rules come first:

- **Target**: the local stack by default. A shared dev/beta environment only with its owner's explicit yes for that
  run (scope, peak rate, duration). Never production, never third-party services, never other people's accounts.
- **No real messages**: tests that request email or SMS codes run only where delivery goes to a test mailbox or is
  stubbed. Hitting a real email/SMS provider at volume costs money and gets the sender blocked.
- Start tiny and ramp; stop at the first sign of harm (errors spreading to other users, provider warnings).

## 1. Script

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [{ duration: '30s', target: 5 }, { duration: '1m', target: 20 }, { duration: '30s', target: 0 }],
  thresholds: { http_req_failed: ['rate<0.01'], http_req_duration: ['p(95)<500'] },
};

export default function () {
  const res = http.get(`${__ENV.BASE_URL}/rest/v1/health`, { headers: { apikey: __ENV.ANON_KEY } });
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(1);
}
```

Run: `BASE_URL=http://127.0.0.1:54321 ANON_KEY=... k6 run --summary-export perf-summary.json script.js`.
Pass secrets through environment variables, never in the script or the report.

## 2. Test types

- **Smoke** (1 user, 1 minute): the script and target work.
- **Load** (expected peak) and **stress** (beyond it, until errors rise): find the breaking point and what breaks.
- **Abuse**: many requests for one email, one IP or one account in a short window. Pass = the limiter answers 429
  (or the documented refusal) after the agreed threshold, other users are unaffected, and the attempts are logged.

## 3. Report

Record the target, commit, data size, script, thresholds and results (p50/p95/p99 latency, error rate, throughput,
where limits kicked in) in the repo's perf or security notes, and compare with the previous run. A threshold miss is
a finding with an owner, not a footnote.
