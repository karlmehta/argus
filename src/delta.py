"""Delta resolver — the incremental-review core. Re-reviews only
`last_reviewed_sha..HEAD` instead of the whole PR, falling back to
`merge-base..HEAD` on a force-push/rebase or first review.
"""
from __future__ import annotations

import os
import subprocess


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=os.environ.get("GITHUB_WORKSPACE", "."),
        capture_output=True, text=True, check=True,
    ).stdout


def _git_ok(*args: str) -> bool:
    return subprocess.run(
        ["git", *args], cwd=os.environ.get("GITHUB_WORKSPACE", "."),
        capture_output=True, text=True,
    ).returncode == 0


def merge_base(a: str, b: str) -> str:
    return _git("merge-base", a, b).strip()


def is_ancestor(a: str, b: str) -> bool:
    return bool(a) and _git_ok("merge-base", "--is-ancestor", a, b)


def resolve_range(base_sha: str, head_sha: str, last_reviewed_sha: str | None, full: bool) -> dict:
    """Return {'start','end':head,'mode'}. mode ∈ first|incremental|refresh(force-push)."""
    if full or not last_reviewed_sha:
        return {"start": merge_base(base_sha, head_sha), "end": head_sha, "mode": "first"}
    if is_ancestor(last_reviewed_sha, head_sha):
        return {"start": last_reviewed_sha, "end": head_sha, "mode": "incremental"}
    return {"start": merge_base(base_sha, head_sha), "end": head_sha, "mode": "refresh"}


def changed_files(rng: dict) -> list[dict]:
    """[{filename, status, additions, deletions}] for the range. Binary files report 0/0."""
    numstat = _git("diff", "--numstat", f"{rng['start']}..{rng['end']}").splitlines()
    status = {}
    for line in _git("diff", "--name-status", f"{rng['start']}..{rng['end']}").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            status[parts[-1]] = parts[0][:1]
    out = []
    for line in numstat:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        adds, dels, name = parts[0], parts[1], parts[-1]
        out.append({
            "filename": name,
            "status": status.get(name, "M"),
            "additions": 0 if adds == "-" else int(adds),
            "deletions": 0 if dels == "-" else int(dels),
        })
    return out


def file_diff(rng: dict, path: str, context: int = 0) -> str:
    """Unified diff hunks for one file in the range."""
    try:
        return _git("diff", f"--unified={context}", f"{rng['start']}..{rng['end']}", "--", path)
    except subprocess.CalledProcessError:
        return ""


def head_file_lines(path: str) -> list[str]:
    """Current (HEAD) content of a file, or [] if deleted/binary/unreadable."""
    full = os.path.join(os.environ.get("GITHUB_WORKSPACE", "."), path)
    try:
        return open(full, encoding="utf-8", errors="replace").read().splitlines()
    except (FileNotFoundError, IsADirectoryError):
        return []
