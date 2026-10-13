---
name: performance
always: false
applies_to: ["**/*model*", "**/*query*", "**/*repository*", "**/dao/**", "**/migrations/**", "**/*.sql", "**/*cache*", "**/*index*", "**/*loop*", "**/*batch*"]
---

# Skill: performance

Flag work that won't scale with data or traffic. Focus on hot paths and anything
touching the database or a loop.

## Checklist
- **N+1 queries:** a query inside a loop over rows; a serializer that lazy-loads a
  relation per item. Look for missing `select_related`/`prefetch`/`JOIN`/batching.
- **Unbounded work:** `.all()` with no pagination/limit; loading a whole table into
  memory; unbounded fan-out; recursion without depth limit.
- **Missing indexes:** new filter/order/join on an unindexed column at scale; a new
  query pattern that no index supports.
- **Hot-path cost:** synchronous network/DB calls, crypto, or serialization on a
  request path that should be fast; work that belongs in a background job.
- **Allocation & copies:** repeated large allocations, quadratic string building,
  copying large structures in a loop, re-compiling regexes per call.
- **Caching:** cacheable expensive computation recomputed every call; cache with no
  invalidation or unbounded growth.
- **Payload size:** endpoints returning far more data than the client needs;
  chatty request patterns.

## Severity guidance
An N+1 or unbounded query on a user-facing path → `major` (or `blocker` if it can
take down the service). Micro-inefficiencies off the hot path → `nit`. Prefer
measuring language: "O(n) DB round-trips where n = number of members."

## Don't
Don't micro-optimize cold paths or readable code for hypothetical gains. Correctness
and clarity win unless there's a real scale concern.
