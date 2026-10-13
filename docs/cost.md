# Argus v2 — cost & telemetry

Every run writes `argus-run.json` (uploaded as a workflow artifact) with exactly
what was sent and what it cost. Read it to debug spend.

## `argus-run.json` shape

```json
{
  "event": "pull_request",
  "pr": 1234,
  "head": "<sha>",
  "rubrics": ["correctness", "security"],
  "pack": {"files_included": ["..."], "files_trimmed": [], "trims": [], "est_input_tokens": 18234, "counted_input_tokens": 17990},
  "triage": {"trivial": false, "risk": "high", "files_for_deep_review": ["..."], "reason": "..."},
  "calls": [
    {"kind": "triage", "model": "claude-haiku-4-5", "usage": {"input_tokens": 400, "cache_read_input_tokens": 16000, "cache_creation_input_tokens": 0, "output_tokens": 180}, "cost_usd": 0.0012},
    {"kind": "review:high", "model": "claude-sonnet-4-6", "usage": {...}, "cost_usd": 0.03}
  ],
  "cost_usd": 0.031,
  "verdict": "COMMENT",
  "result": "reviewed",
  "spend_pr_usd": 0.12
}
```

`result` is one of: `reviewed`, `trivial`, `gated`, `superseded`, `summary_only`,
`daily_budget_stop`, `pr_budget_stop`, `per_run_budget_stop`.

## Cost formula

Per call, from `src/pricing.json` ($/MTok):

```
cost = in/1e6*input + out/1e6*output
     + cache_write/1e6*cache_write + cache_read/1e6*cache_read
```

`cache_read` is ~10x cheaper than fresh input, so a high **cache-read ratio** (the
`% cached` in the summary comment) is where most of the savings come from — the
stable prefix (system + rubrics + memory) is cached for 1h and reused across a
repo's PRs/pushes.

## Where to cut cost further

- Raise `min_confidence` / lower `max_input_tokens` / shrink `context_lines`.
- Narrow rubric `applies_to` globs so fewer rubrics load per PR.
- Keep `review_default: claude-haiku-4-5`; only high-risk deltas escalate to Sonnet.
- Watch `result: pr_budget_stop` / `daily_budget_stop` — those are the guardrails
  firing; tune `budget.*` in config.

## Budgets

`budget.per_run_usd` aborts before the review call if the pre-count estimate
exceeds it. `budget.per_pr_usd` (summed in the PR's state marker) flips a PR to
summary-only. `budget.per_repo_daily_usd` (tracked on the `argus-state` branch)
pauses the repo for the day. All three are checked before any model call.
