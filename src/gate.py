"""No-LLM gating. Decides whether to review at all, and in what mode, before any
model call — so a draft/bot/lockfile-only/oversized PR costs nothing."""
from __future__ import annotations

from . import globs

DEFAULT_SKIP_GLOBS = [
    "**/*.lock", "**/package-lock.json", "**/yarn.lock", "**/pnpm-lock.yaml", "**/poetry.lock",
    "**/*.min.js", "**/*.map", "**/dist/**", "**/build/**", "**/generated/**",
    "**/__generated__/**", "**/__snapshots__/**", "**/*.snap",
    "**/*.svg", "**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.gif", "**/*.pdf", "**/*.ico",
    "**/vendor/**", "**/node_modules/**",
]

BOT_AUTHORS = {"dependabot[bot]", "renovate[bot]", "github-actions[bot]", "argus[bot]", "claude[bot]"}


def skip_globs(config: dict) -> list[str]:
    return DEFAULT_SKIP_GLOBS + (config.get("skip_globs") or config.get("paths", {}).get("skip") or [])


def non_skipped(changed_files: list[dict], config: dict) -> list[dict]:
    sk = skip_globs(config)
    return [f for f in changed_files if not globs.matches_any(f["filename"], sk)]


def changed_lines(files: list[dict]) -> int:
    return sum((f.get("additions", 0) + f.get("deletions", 0)) for f in files)


def evaluate(pr: dict, changed_files: list[dict], config: dict) -> dict:
    """Return {action, reason, [note]}. action ∈ skip | summary_only | proceed."""
    if pr.get("draft"):
        return {"action": "skip", "reason": "draft PR"}

    author = (pr.get("user") or {}).get("login", "")
    if author in BOT_AUTHORS and not config.get("review_bots", False):
        return {"action": "skip", "reason": f"bot author {author}"}

    reviewable = non_skipped(changed_files, config)
    if not reviewable:
        return {"action": "skip", "reason": "only ignored paths changed"}

    max_lines = config.get("max_changed_lines", 800)
    n = changed_lines(reviewable)
    if n > max_lines:
        return {
            "action": "summary_only",
            "reason": f"{n} changed lines > max_changed_lines ({max_lines})",
            "note": "This PR is large — Argus posts a summary + high-risk file list and asks for a split instead of a full review.",
        }

    return {"action": "proceed", "reason": f"{n} reviewable changed lines in {len(reviewable)} files"}
