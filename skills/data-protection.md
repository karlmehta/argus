---
name: data-protection
always: false
applies_to: ["**/*user*", "**/*patient*", "**/*pii*", "**/*export*", "**/*serializer*", "**/*log*", "**/payments/**", "**/*email*", "**/*phone*", "**/*address*", "**/*.sql", "**/migrations/**"]
---

# Skill: data-protection

Guard personal and cross-tenant data. This overlaps with `security` but is scoped
to *what data is exposed to whom*, including accidental leakage through responses,
logs, and analytics.

## Checklist
- **Over-broad responses:** A serializer/DTO that newly includes PII, internal ids,
  tokens, hashes, or other tenants' fields. Adding a field to a shared serializer is
  a common silent leak → check who consumes it.
- **Cross-tenant leakage:** List endpoints or joins that can return rows outside the
  caller's tenant/org. Aggregates computed across tenants.
- **Sensitive logging:** Emails, tokens, full request bodies, auth headers, card/PII
  written to logs or error trackers → `major`. Structured logs that interpolate
  user records wholesale.
- **Analytics / third parties:** New events sent to analytics/telemetry that include
  PII or full payloads. Client-side beacons carrying identifiers.
- **Retention & consent:** New long-lived storage of personal data without a
  deletion path; storing more than the feature needs (data minimization).
- **Encryption at rest/in transit:** New sensitive columns stored plaintext; secrets
  in DB without envelope encryption; downgrade to non-TLS transports.
- **PII in fixtures/tests:** Real names/emails/keys in test data.

## Severity guidance
A response or log path that leaks another user's/tenant's PII → `blocker`. Excess
PII in logs/analytics → `major`. Minimization/retention improvements → `minor`.

## Tie-in with memory
If `memory/conventions.md` documents which fields are "public-safe," enforce it.
Adding a non-listed field to a public serializer is at least `major`.
