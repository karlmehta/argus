---
name: observability
always: false
applies_to: ["**/*log*", "**/*error*", "**/*exception*", "**/*metric*", "**/*trace*", "**/*monitor*", "**/*sentry*", "**/*alert*"]
---

# Skill: observability

When this breaks in production at 3am, will anyone be able to tell? Review logs,
metrics, traces, and failure visibility.

## Checklist
- **Silent failures:** caught exceptions with no log/metric; empty `except`;
  fallbacks that hide the real error; a degraded path that looks like success.
  A silently-swallowed error on an important path → `major`.
- **Actionable logs:** new error paths should log enough context (ids, not PII) to
  diagnose. Avoid logging in tight loops (spam) and avoid logging secrets/PII (see
  `data-protection`).
- **Metrics:** new critical operations (payments, deploys, external calls) should
  emit success/failure counters and latency. New failure modes need a signal an
  alert could fire on.
- **Tracing:** new external/DB calls on a traced path should be spanned; context
  propagation not dropped across async/queue boundaries.
- **Health & readiness:** new hard dependency added to a request path but not to
  health checks; startup failure that isn't surfaced.
- **Error messages:** returned errors are actionable (not `"error"`); correlation
  id preserved.

## Severity guidance
A new failure mode that is completely invisible (no log, no metric) on a critical
path → `major`. Missing latency metric on a new external call → `minor`.

## Don't
Don't ask for logging on trivial pure functions. Signal, not noise — over-logging is
its own bug.
