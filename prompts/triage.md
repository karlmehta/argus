# Triage

Classify the delta under review. Return the `triage` tool object only.

- `trivial`: true only if nothing here could change behavior or risk — pure
  formatting, comments, docs, dependency version bumps with no code change,
  generated files. When in doubt, `trivial: false`.
- `risk`:
  - `high` — touches auth, permissions, tenancy, secrets/credentials, SQL or data
    migrations, money/payments, concurrency/locking, crypto, or a public API /
    exported contract; or deletes safety checks.
  - `medium` — ordinary application logic, non-trivial behavior change.
  - `low` — small, local, low-blast-radius changes; tests; config.
- `files_for_deep_review`: the specific changed files that carry the high-risk
  surface. Empty for low/medium.
- `reason`: ≤2 sentences.

Judge only from the provided diff, context, and symbols. Do not assume unseen code.
