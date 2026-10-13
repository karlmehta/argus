---
name: concurrency
always: false
applies_to: ["**/*async*", "**/*await*", "**/*worker*", "**/*queue*", "**/*task*", "**/tasks.py", "**/*lock*", "**/*thread*", "**/*mutex*", "**/*transaction*", "**/*atomic*", "**/*goroutine*", "**/*channel*"]
---

# Skill: concurrency

Reason about what happens when two of these run at once. Most concurrency bugs are
invisible in a single-threaded read of the diff.

## Checklist
- **Read-modify-write races:** `x = get(); x.n += 1; save(x)` without a lock,
  `select_for_update`, atomic increment, or optimistic-concurrency check. Two
  requests → lost update → `major`/`blocker` if it touches money/counters/state.
- **Check-then-act:** `if not exists(): create()` without a unique constraint or
  `get_or_create` → duplicate rows under race.
- **Shared mutable state:** module-level/global caches, singletons, class attrs
  mutated per-request; thread-unsafe clients reused across threads.
- **Transaction scope:** work that must be atomic split across transactions;
  side effects (emails, webhooks, queue publishes) inside a transaction that can
  roll back → duplicate/false sends. Prefer transactional outbox.
- **Locks:** lock ordering that can deadlock; locks held across I/O; sleeping/polling
  where an event/lock is appropriate.
- **Async:** unawaited coroutines/promises, fire-and-forget without error capture,
  blocking calls on an async event loop, cancellation not handled.
- **Idempotency keys:** retried operations (webhooks, jobs) without a dedupe key.

## Severity guidance
Lost update / duplicate on money, orders, memberships, credits → `blocker`.
Race producing a rare duplicate that's cleaned up elsewhere → `major`/`minor`.

## Method
For each new write, ask: "two requests, interleaved — what breaks?" Name the
interleaving in the finding so the author can see it.
