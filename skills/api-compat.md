---
name: api-compat
always: false
applies_to: ["**/api/**", "**/*.proto", "**/openapi*", "**/schema*", "**/migrations/**", "**/routes/**", "**/urls.py", "**/*serializer*", "**/*controller*", "**/*endpoint*", "**/*.graphql"]
---

# Skill: api-compat

Catch changes that break existing callers, clients, stored data, or in-flight
deploys. These bugs land *after* merge, so reviewers miss them.

## Checklist
- **HTTP/RPC contracts:** removed/renamed field, changed type, changed status code,
  new required request param, tightened validation, changed default, changed
  pagination/error shape. Any of these breaks existing clients → `major`/`blocker`.
- **Backward/forward compat during deploy:** does old code run against the new DB
  and vice-versa during a rolling deploy? A migration that drops/renames a column
  the currently-running code still reads → `blocker`.
- **Migration collisions:** two migrations with the same number/parent; a data
  migration that assumes a column added in the same PR's later migration; a
  long/locking migration on a big table without a safe strategy.
- **Serialization / persisted data:** enum/const values renamed while old values
  exist in the DB or queues; message-schema changes that break in-flight messages;
  cache-key format changes that don't invalidate.
- **Public SDK / library surface:** exported symbol removed/renamed, signature
  change, changed semantics without a version bump; changelog missing.
- **Config/flags:** renamed env var/flag without a fallback; default flip that
  changes behavior for existing installs.

## Severity guidance
Breaks a live client, drops data, or breaks a rolling deploy → `blocker`. Breaks an
internal caller you can update in the same PR → `major` (and check they updated it).

## Method
For each removed/renamed/retyped symbol or field, grep for callers. For each
migration, ask "does the previous release's code survive this?"
