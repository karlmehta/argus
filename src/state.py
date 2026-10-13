"""Argus v2 persistent state — no external store.

Per-PR state (last reviewed SHA, carried findings, cumulative spend) lives in a
hidden marker inside Argus's single summary comment, so it round-trips through the
PR itself. Per-repo daily spend lives in a tiny JSON on an orphan `argus-state`
branch (best-effort; a read/write failure never blocks a review).
"""
from __future__ import annotations

import base64
import json
import re
from typing import Any

from . import gh

MARKER_RE = re.compile(r"<!--\s*argus-state\s*(\{.*?\})\s*-->", re.DOTALL)
STATE_BRANCH = "argus-state"


def marker(state: dict) -> str:
    return f"<!-- argus-state {json.dumps(state, separators=(',', ':'))} -->"


def find_summary_comment(pr_number: int) -> tuple[int | None, str]:
    """Return (comment_id, body) of Argus's summary comment, or (None, '')."""
    comments = gh.paginate(gh.repo_path(f"/issues/{pr_number}/comments"), params={"per_page": 100})
    for c in comments:
        if MARKER_RE.search(c.get("body") or ""):
            return c["id"], c["body"]
    return None, ""


def read_state(pr_number: int) -> dict[str, Any]:
    cid, body = find_summary_comment(pr_number)
    m = MARKER_RE.search(body or "")
    state: dict[str, Any] = {"version": 2, "last_reviewed_sha": None, "findings": [], "spend_usd": 0.0}
    if m:
        try:
            state.update(json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass
    state["_comment_id"] = cid
    return state


# ── per-repo daily spend (best-effort, on the argus-state branch) ─────────────

def _state_file_path(day: str) -> str:
    return f"daily-spend/{day}.json"


def read_daily_spend(day: str) -> float:
    try:
        path = _state_file_path(day)
        res = gh.get(gh.repo_path(f"/contents/{path}"), params={"ref": STATE_BRANCH})
        content = base64.b64decode(res["content"]).decode()
        return float(json.loads(content).get("spend_usd", 0.0))
    except Exception:
        return 0.0  # branch/file absent or unreadable — treat as zero, fail open


def add_daily_spend(day: str, amount: float) -> None:
    """Increment the day's total. Soft-fails: spend tracking must never block review."""
    try:
        path = _state_file_path(day)
        sha = None
        current = 0.0
        try:
            res = gh.get(gh.repo_path(f"/contents/{path}"), params={"ref": STATE_BRANCH})
            sha = res["sha"]
            current = float(json.loads(base64.b64decode(res["content"]).decode()).get("spend_usd", 0.0))
        except Exception:
            pass
        body = {
            "message": f"argus: daily spend {day}",
            "content": base64.b64encode(json.dumps({"day": day, "spend_usd": round(current + amount, 4)}).encode()).decode(),
            "branch": STATE_BRANCH,
        }
        if sha:
            body["sha"] = sha
        gh.put(gh.repo_path(f"/contents/{path}"), body)
    except Exception:
        pass
