---
name: correctness
always: true
applies_to: []
---

# Skill: correctness

Does it work, and does it do what the PR says? Trace real execution, don't
pattern-match.

## Checklist
- **Intent match:** Compare the diff to the PR description. Silent scope creep or a
  change that doesn't achieve the stated goal is a finding.
- **Edge cases:** null/None/undefined, empty collections, zero/negative numbers,
  first/last iteration, single-element vs many, timezone/DST, unicode, very large
  inputs.
- **Off-by-one & boundaries:** ranges, slicing, pagination, retries/backoff counters.
- **Error handling:** swallowed exceptions (`except: pass`), errors logged but not
  handled, missing rollback on failure, partial writes, resource leaks (unclosed
  files/connections), `finally` correctness.
- **Control flow:** unreachable branches, inverted conditions, missing `return`,
  fallthrough, early-return that skips cleanup.
- **State & idempotency:** operations assumed idempotent that aren't (retried
  webhooks, at-least-once queues); non-deterministic ordering assumed stable.
- **Data & types:** implicit type coercion, float equality, integer overflow,
  serialization round-trips, enum/string drift between layers.
- **Contracts:** function called with args it doesn't handle; nullable return used
  as non-null; new code path that violates an invariant asserted elsewhere.

## Method
Pick the happy path + the two edge cases most likely to occur in production and
narrate them line by line. If a bug depends on caller behavior, open the caller.

## Severity guidance
Wrong result, data loss/corruption, crash on a common path → `blocker`. Bug on an
uncommon-but-real path → `major`. Fragile-but-currently-correct → `minor`.
