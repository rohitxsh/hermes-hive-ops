---
name: test-first
description: >-
  Write tests worth keeping when building a feature or fixing a bug test-first: agree the few seams to test,
  then work red → green one vertical slice at a time, and avoid tests that are tied to internals, pass by
  construction or test imagined behavior. Use when you write or review tests for a ticket (dev and QA), when a PR
  adds many tests, or when someone says TDD or red-green. Complements test-driven-development; this one is about
  which tests to write and which to leave out.
license: MIT (adapted from mattpocock/skills `tdd`, see LICENSE)
---

# Test first, at the seams

The goal is a small set of tests that pin down what the ticket promises and survive refactors. More tests are not
better: every test is code someone maintains, runs in CI and reads in review. A PR whose test count is several times
its acceptance criteria needs a reason.

## 1. Agree the seams before writing tests

A **seam** is the public boundary you test at: a function or class other code calls, a repository method, a widget a
screen shows, an RPC or RLS policy, a CLI command. Tests live at seams, never against internals.

- Take the seams from the ticket or PRD (its "Testing decisions"). If it names none, pick the highest existing seam
  that shows the behavior; the fewer seams the better, ideally one per ticket.
- Write them on the card before the first test, one line each: what it catches, what it misses. Don't ask a person
  to confirm them; QA checks them in review. Ask only if the ticket is genuinely ambiguous about what behavior it wants.
- Each acceptance criterion maps to at least one test at a seam. A test that maps to no criterion and no known bug is
  probably not needed.

## 2. The loop: one vertical slice at a time

- **Red before green.** Write one failing test at an agreed seam, run it and see it fail for the right reason, then
  write only enough code to pass it.
- **One slice per cycle.** One seam, one test, one minimal change. Let what this cycle taught you shape the next test.
  Don't write all the tests first and then all the code: bulk tests check imagined behavior and lock in structure
  before you understand it.
- **Refactor in review, not in the loop.** Clean up once the slice is green, as its own step.

## 3. What a good test looks like

- Describes behavior the caller cares about, named for WHAT happens ("rider can book a seat on a ride with free
  seats"), not HOW.
- Uses only the public interface and survives an internal rewrite.
- One logical assertion; expected values come from an independent source (a literal, a worked example, the spec).

```dart
// GOOD: behavior through the public interface
test('booking the last free seat marks the ride full', () async {
  final ride = await rides.create(seats: 1);
  await bookings.book(rideId: ride.id, riderId: rider.id);
  expect((await rides.get(ride.id)).isFull, isTrue);
});

// BAD: reaches past the interface into the table
test('book inserts a row', () async {
  await bookings.book(rideId: ride.id, riderId: rider.id);
  final rows = await db.from('bookings').select().eq('ride_id', ride.id);
  expect(rows, isNotEmpty);
});
```

## 4. Anti-patterns to flag (write them or review them)

- **Tied to internals:** mocks your own classes, tests private methods, asserts call counts or order, or checks through
  a side channel (querying the database instead of the interface). Tell: it breaks on a refactor that changed no behavior.
- **Passes by construction (tautological):** the expected value is computed the way the code computes it, a snapshot
  regenerated from the code, a constant compared with itself.

  ```dart
  // BAD: always agrees with the code
  expect(fareFor(trip), trip.km * ratePerKm);
  // GOOD: an independent known value
  expect(fareFor(Trip(km: 12)), 180);
  ```

- **Horizontal slicing:** all tests first, then all code (see §2).
- **Test sprawl:** many near-identical cases for one rule, or tests for code the ticket didn't touch. Use one table-
  driven test for variations of the same rule.

## 5. Mocking

Mock only at system boundaries you don't control: external APIs (payments, SMS, email), time and randomness, sometimes
the file system. Prefer a real local or test database (the local Supabase stack) over mocking the database. Don't mock
your own modules. To make boundaries easy to fake, pass the client in (dependency injection) and give it one method per
operation (`sendOtp`, `chargeFare`) instead of one generic `request(endpoint, …)`.

## For QA

Check that each acceptance criterion is covered at an agreed seam, that no test is tied to internals or passes by
construction, and that the test count is proportionate. Ask for removal of sprawl as you would for any other defect.
