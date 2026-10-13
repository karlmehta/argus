---
name: tests
always: true
applies_to: []
---

# Skill: tests

Judge whether the change is *verified*, not just whether tests exist.

## Checklist
- **Coverage of new behavior:** every new branch/edge case the PR introduces should
  have a test that would fail without the change. New logic with zero tests →
  `major` (or `minor` for trivial/mechanical changes).
- **Meaningful assertions:** tests that assert nothing, assert on mocks only, or
  re-implement the code under test are tautological → call them out.
- **Bug fixes need a regression test:** a fix without a test that reproduces the bug
  will regress. Ask for one.
- **Edge cases from `correctness`:** the null/empty/boundary cases you flagged —
  are any tested? Cross-reference.
- **Test quality:** over-mocking that hides integration bugs; time/order/network
  flakiness; shared mutable fixtures; tests that only pass in a specific order.
- **Security/authorization tests:** new permission checks should have a
  "forbidden" test, not just a "happy path" one.
- **Negative space:** error paths, failure injection, and rollback behavior tested?

## Severity guidance
Untested security/authorization logic or untested money/data-mutation path →
`major`. Untested ordinary branch → `minor`. Missing regression test on a bug fix →
`major` (it *will* come back).

## Don't
Don't demand 100% coverage or tests for pure refactors with existing coverage. Ask
for the tests that would have caught a real bug.
