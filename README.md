<div align="center">

# 🛡️ Argus

### The AI code reviewer that *actually reviews.*

[![release](https://img.shields.io/github/v/release/karlmehta/argus?color=7c3aed)](https://github.com/karlmehta/argus/releases)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)
[![built with Claude](https://img.shields.io/badge/built%20with-Claude-8A2BE2)](https://www.anthropic.com/claude)
[![stars](https://img.shields.io/github/stars/karlmehta/argus?style=social)](https://github.com/karlmehta/argus/stargazers)

**Argus** is a self-hostable, model-agnostic PR reviewer for GitHub. It reads your diff the way a senior engineer does — across security, data-protection, correctness, performance, tests, and API-compatibility — remembers your codebase's conventions between reviews, and leaves a precise, cited, severity-ranked verdict instead of a rubber stamp.

Named for [Argus Panoptes](https://en.wikipedia.org/wiki/Argus_Panoptes), the hundred-eyed watchman who never slept.

> **v2 — token-efficient.** Argus is now a **deterministic pipeline**, not an open-ended agent: scripts gather a minimal context pack, a cheap model triages, and only high-risk files escalate to a stronger model — **1–2 model calls per run, the model never uses tools.** Incremental re-reviews, a cache-stable prompt prefix, path-matched rubrics, and per-run/PR/repo budgets cut cost by ~90% with no loss in blocker/major recall. Design: [`docs/v2.md`](docs/v2.md) · cost telemetry: [`docs/cost.md`](docs/cost.md).

[Quickstart](#-quickstart) · [How it works](#-how-it-works) · [Skills](#-skills) · [Memory](#-memory) · [Governance](docs/governance.md) · [Configuration](docs/configuration.md)

</div>

---

## Why Argus

Most "AI PR review" bots summarize the diff and post a few generic nits. Argus is built on three ideas that make it a reviewer you'd actually trust:

1. **Skills, not vibes.** Review is decomposed into explicit, versioned *skills* — each a focused rubric a specialist would apply (a security lens, a data-protection lens, a concurrency lens…). You enable the ones your repo needs and write your own. Findings are traceable to the skill that raised them.
2. **Memory.** Argus persists what it learns about *your* repo — conventions, accepted patterns, known false-positives, past decisions — and loads it into every review. It gets quieter and sharper over time instead of re-litigating the same nit on every PR.
3. **An honest verdict.** Every finding carries a **severity** (`blocker` / `major` / `minor` / `nit`) and a file:line citation. Argus **requests changes** when it finds a real blocker and **approves** only when it genuinely would sign off — and *never* to merely clear a gate. Whether that approval counts toward your branch protection is *your* governance decision, documented in [`docs/governance.md`](docs/governance.md).

> **Argus is a force-multiplier for human review, not a replacement for it.** It catches the boring 80% so your reviewers spend their attention on the 20% that needs judgment. See [Governance](docs/governance.md) for how to wire it in without weakening branch protection.

---

## ✨ Quickstart

**1. Add a dedicated key.** Give Argus its own Anthropic key — a separate Console workspace with a spend limit, so review spend is tracked and bounded. Add it as a repo (or org) secret:

```bash
gh secret set ARGUS_ANTHROPIC_API_KEY --repo <owner>/<repo>
```

**2. Drop in the caller** (`.github/workflows/argus.yml`) — it owns the triggers; the reusable workflow owns the pipeline. **Pin to a SHA** (the rubrics in force are the rubrics that were reviewed):

```yaml
name: Argus review
on:
  pull_request:
    types: [opened, reopened, ready_for_review, synchronize]
  issue_comment:
    types: [created]        # OWNER/MEMBER/COLLABORATOR can type "@argus review"
jobs:
  argus:
    uses: karlmehta/argus/.github/workflows/argus-review.yml@<pin-a-sha>
    with:
      harness-ref: <pin-the-same-sha>
      config-path: .github/argus/config.yml
    secrets:
      ARGUS_ANTHROPIC_API_KEY: ${{ secrets.ARGUS_ANTHROPIC_API_KEY }}
```

**3. Open a PR.** Argus posts a review, with a cost line, within a minute or two. That's it. Ready-to-copy caller: [`examples/caller-argus.yml`](examples/caller-argus.yml).

**Per-repo config & memory** live in *your* repo at `.github/argus/` — `config.yml` (skills, models, budgets, globs) and `memory/{conventions,accepted-patterns}.md`. Memory is **not** shared across repos. Roll out staged (shadow `dry_run` → canary) per [`docs/v2.md`](docs/v2.md).

---

## 🔭 How it works (v2)

A deterministic pipeline — **the model never uses tools.** Scripts gather context and post results; the model receives one prompt and returns one JSON object. **1–2 model calls per run.**

```
  PR event (opened | ready_for_review | synchronize | "@argus")
      │
      ▼  debounce        on a push, wait a quiet period; a superseded run makes ZERO model calls
      ▼  gate            draft / bot / lockfile-only / oversized → short-circuit, no LLM
      ▼  delta           review only last_reviewed_sha..HEAD; trivial/empty delta → note, no LLM
      ▼  context pack    diff hunks + ±N HEAD context + referenced-symbol signatures
      │                  + ONLY path-matched rubrics + repo memory  (cache-stable prefix, 1h cache)
      ▼  triage  (Haiku, 1 call) → trivial? risk = low|medium|high
      ▼  review          low/medium → Haiku · high → Sonnet, scoped to the risky files   (1 call)
      ▼  merge           carry forward unresolved prior findings, drop stale, dedupe, confidence-filter
      ▼  post            review bound to commit_id (verdict + inline) + one editable summary + cost line
      ▼  record          argus-run.json: exactly what was sent + what it cost
```

Budgets (per-run / per-PR / per-repo-daily) are checked **before any model call**. Full design + rollout in [`docs/v2.md`](docs/v2.md); internals in [`docs/architecture.md`](docs/architecture.md).

---

## 👀 What a review looks like

> Posted by `argus[bot]` on a real PR — every finding is severity-tagged and cited.

```markdown
## 🛡️ Argus review

**Verdict:** REQUEST CHANGES  ·  1 blocker · 1 major · 2 minor · 1 nit

### Findings
| Sev | Skill | Location | Finding |
|-----|-------|----------|---------|
| 🔴 blocker | security | api/invites/views.py:212 | `Invite.objects.get(pk=…)` isn't scoped to the caller's org → any user can accept another org's invite by id (IDOR). Scope by `request.user`'s org. |
| 🟠 major | concurrency | billing/credits.py:88 | `c = get(); c.balance -= n; c.save()` is a non-atomic read-modify-write — two concurrent spends lose an update. Use `select_for_update()` or an atomic `F()` decrement. |
| 🟡 minor | tests | — | The new `expired` branch in `accept()` has no test; add one that would fail without the guard. |
| 🟡 minor | observability | tasks/webhook.py:41 | `except Exception: pass` swallows delivery failures silently — log with the event id. |
| ⚪ nit | correctness | serializers.py:19 | Redundant `list()` around a comprehension. |

### Questions
- `serializers.py:33` adds `email` to `PublicUserSerializer` — is this serializer used on any unauthenticated endpoint? If so it's a data-protection blocker.

### 📝 Memory suggestion
- You've accepted raw SQL in `analytics/queries/` twice now — want me to add it to `accepted-patterns.md` so I stop flagging it?
```

---

## 🆚 Why not just a summarizer bot?

| | Generic "AI review" bot | **Argus** |
|---|---|---|
| Output | prose summary + a few nits | severity-ranked, `file:line`-cited findings per skill |
| Consistency | different every run | explicit, versioned **skills** you can read and extend |
| False positives | forever | **memory** kills repeats; a calibration pass cuts low-confidence noise |
| Trust to block/approve | none | honest verdict + documented **governance** (approval off by default) |
| Ownership | opaque prompt | skills/prompts/memory/config are Markdown **in your repo** |

---

## 🧠 Skills

Each skill is a small, self-contained rubric in [`skills/`](skills). Ships with:

| Skill | What it hunts for |
|---|---|
| [`security`](skills/security.md) | authz/authn gaps, injection, SSRF, secrets, IDOR, missing tenant-scoping, unsafe deserialization |
| [`data-protection`](skills/data-protection.md) | PII exposure, over-broad querysets, cross-tenant leakage, sensitive logging, retention/consent |
| [`correctness`](skills/correctness.md) | logic bugs, null/empty/off-by-one, error handling, race-y assumptions, "does it do what the PR says" |
| [`concurrency`](skills/concurrency.md) | races, deadlocks, non-atomic read-modify-write, unguarded shared state |
| [`performance`](skills/performance.md) | N+1 queries, unbounded loops/allocations, missing indexes, sync work on hot paths |
| [`api-compat`](skills/api-compat.md) | breaking API/schema changes, migration collisions, client-contract drift |
| [`tests`](skills/tests.md) | is the change covered? are the tests meaningful or tautological? |
| [`observability`](skills/observability.md) | missing/incorrect logs, metrics, traces; silent failure paths |
| [`dependencies`](skills/dependencies.md) | risky new deps, license issues, version pins, supply-chain smell |

Writing your own is a markdown file and one line of config — see [`docs/configuration.md`](docs/configuration.md#writing-a-skill).

---

## 💾 Memory

Argus keeps a durable, human-readable memory in [`memory/`](memory) that it loads into every review:

- **`conventions.md`** — how *this* repo does things (patterns to enforce, patterns that are fine here).
- **`accepted-patterns.md`** — "yes, we know, this is intentional" — kills repeat false-positives.
- **`knowledge/`** — accumulated, curated learnings (past incidents, gotchas, subsystem notes).

Memory is just Markdown in your repo — reviewable, diff-able, and owned by you. Argus can *propose* additions (e.g. "you accepted this pattern 3× — add it to accepted-patterns?") as a suggestion; a human merges it. Full model in [`docs/memory.md`](docs/memory.md).

---

## 🔒 Governance & the "second reviewer" question

Argus renders a genuine verdict. Whether `argus[bot]`'s **approval** is allowed to *satisfy a required review* is a branch-protection setting **you** own — and there are honest, non-footgun ways to wire it (require Argus **plus** a human; require Argus only on low-risk paths; Argus as a required *status check* rather than an approver). We lay out the trade-offs, and the ways this can quietly defeat human review, in [`docs/governance.md`](docs/governance.md). Read it before you let a bot approve your own PRs.

---

## Configuration

Everything is driven by [`config/argus.yml`](config/argus.yml) (your repo overrides it at `.github/argus/config.yml`): which skills are eligible, per-stage **models** (triage / default / high-risk), **budgets** (`per_run_usd` / `per_pr_usd` / `per_repo_daily_usd`), `strict_globs` (force the stronger model), `skip_globs`, the severity `gate`, `dry_run` (shadow mode), and `verdict.allow_approve`. Each skill declares `applies_to` globs so only relevant rubrics load per PR. See [`docs/configuration.md`](docs/configuration.md) and [`docs/cost.md`](docs/cost.md).

---

## License

[MIT](LICENSE). Use it, fork it, ship it.

## Contributing

New skills, better prompts, adapters for other CI systems — all welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md).
