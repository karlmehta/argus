# Configuration

> **v2 note.** v2 adds keys this page may not list yet: `models` (triage /
> review_default / review_high_risk), `budget` (per_run_usd / per_pr_usd /
> per_repo_daily_usd), `debounce_minutes`, `context_lines`, `max_input_tokens`,
> `min_confidence`, `strict_globs`, `skip_globs`, and `dry_run` (shadow mode). Each
> skill also carries `applies_to` front-matter so only matching rubrics load. The
> v1 keys below (`paths.skip` / `paths.strict` / `limits.*`) are still honored. See
> the commented [`config/argus.yml`](../config/argus.yml) and [`v2.md`](v2.md).

All behavior is driven by [`config/argus.yml`](../config/argus.yml).

## Keys

| Key | Meaning |
|---|---|
| `skills` | Ordered list of enabled skills (each maps to `skills/<name>.md`). |
| `gate` | Lowest severity that triggers `request-changes` (`blocker`/`major`/`minor`). |
| `verdict.allow_approve` | Whether Argus may submit an APPROVE review. Default `false`. See [governance](governance.md). |
| `verdict.never_approve_authors` | Authors whose PRs are never approved (bots). |
| `paths.skip` | Globs excluded from review entirely. |
| `paths.strict` | Globs where every finding is bumped one severity and security/data-protection get extra scrutiny. |
| `limits.max_inline_comments` | Cap on inline comments before the rest roll into the summary. |
| `limits.max_diff_lines` | PRs larger than this get a "please split" note instead of a shallow review. |
| `model` | Model override; empty inherits the action default. |

## Choosing a model
- **Deep reviews / high-stakes repos:** a top-tier model (e.g. `claude-opus-4-8`).
- **High PR volume / cost-sensitive:** a faster model; keep Opus for `strict:` paths
  by running two jobs with different configs.

## Writing a skill
A skill is a Markdown rubric. To add one:

1. Create `skills/my-skill.md`. Structure it like the built-ins:
   - a one-line purpose,
   - a **Checklist** of concrete things to look for,
   - **Severity guidance** (what's a blocker vs nit for this lens),
   - a **Don't** section to prevent false positives.
2. Add `- my-skill` to `skills:` in `config/argus.yml`.
3. Open a PR — Argus will review its own new skill.

Good skills are *specific* and *falsifiable*. "Check for bad code" is useless;
"flag a query inside a loop over rows (N+1)" is a skill. Encode the judgment your
best reviewer applies for that lens.

## Per-directory configs
For a monorepo, keep multiple configs (e.g. `config/argus.backend.yml`,
`config/argus.frontend.yml`) and pass `config-path` per job so each area runs the
skills that fit it.
