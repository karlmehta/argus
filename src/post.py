"""Post results to GitHub (no LLM): one review bound to the head commit (carries the
verdict + inline comments) and one editable summary comment (table, cost, hidden
state marker). Verdict policy is unchanged from v1."""
from __future__ import annotations

import os

from . import gh, state


def _dry() -> bool:
    """Shadow mode — compute everything, post nothing (spec §9 shadow stage)."""
    return os.environ.get("ARGUS_DRY_RUN") == "1"

SEV_ICON = {"blocker": "🔴", "major": "🟠", "minor": "🟡", "nit": "⚪"}
SEV_RANK = {"blocker": 0, "major": 1, "minor": 2, "nit": 3}


def choose_verdict(findings: list[dict], pr: dict, config: dict) -> str:
    """Return a GitHub review event: REQUEST_CHANGES | COMMENT | APPROVE."""
    gate = config.get("gate", "major")
    gate_rank = SEV_RANK.get(gate, 1)
    gating = [f for f in findings if SEV_RANK.get(f.get("severity"), 3) <= gate_rank]
    if gating:
        return "REQUEST_CHANGES"

    vcfg = config.get("verdict", {})
    author = (pr.get("user") or {}).get("login", "")
    never = set(vcfg.get("never_approve_authors", []))
    if vcfg.get("allow_approve") and author not in never and not gating:
        return "APPROVE"
    return "COMMENT"


def _inline_comments(findings: list[dict], config: dict) -> list[dict]:
    max_inline = config.get("max_inline_comments", config.get("limits", {}).get("max_inline_comments", 10))
    inlineable = [f for f in sorted(findings, key=lambda f: SEV_RANK.get(f.get("severity"), 3))
                  if f.get("severity") in ("blocker", "major", "minor") and f.get("file") and f.get("line")]
    out = []
    for f in inlineable[:max_inline]:
        out.append({
            "path": f["file"],
            "line": int(f["line"]),
            "side": "RIGHT",
            "body": f"**{SEV_ICON.get(f['severity'],'')} {f['severity']} · {f.get('skill','')}** — {f.get('title','')}\n\n{f.get('body','')}",
        })
    return out


def _summary_body(pr: dict, head_sha: str, verdict: str, findings: list[dict], summary: str,
                  cost_line: str, trims: list[str], marker: str) -> str:
    counts = {s: sum(1 for f in findings if f.get("severity") == s) for s in SEV_ICON}
    tally = " · ".join(f"{counts[s]} {s}" for s in ("blocker", "major", "minor", "nit"))
    label = {"REQUEST_CHANGES": "REQUEST CHANGES", "APPROVE": "APPROVE", "COMMENT": "COMMENT"}[verdict]
    lines = [
        "## 🛡️ Argus review",
        "",
        f"**Verdict:** {label}  ·  {tally}  ·  `{head_sha[:8]}`",
        "",
        summary.strip(),
        "",
    ]
    if findings:
        lines += ["### Findings", "| Sev | Skill | Location | Finding |", "|-----|-------|----------|---------|"]
        for f in sorted(findings, key=lambda f: SEV_RANK.get(f.get("severity"), 3)):
            loc = f"{f.get('file','—')}:{f.get('line','')}" if f.get("file") else "—"
            lines.append(f"| {SEV_ICON.get(f.get('severity'),'')} {f.get('severity')} | {f.get('skill','')} | {loc} | {f.get('title','')} |")
        lines.append("")
    if trims:
        lines += ["> ⚠️ **Not deeply reviewed** (token budget): " + "; ".join(trims), ""]
    lines += [f"<sub>{cost_line}</sub>", "", marker]
    return "\n".join(lines)


def publish(pr: dict, head_sha: str, findings: list[dict], summary: str, config: dict,
            new_state: dict, cost_line: str, trims: list[str]) -> str:
    """Submit the review (verdict + inline) and upsert the summary comment. Returns verdict."""
    pr_number = pr["number"]
    verdict = choose_verdict(findings, pr, config)
    if _dry():
        return verdict  # shadow: artifact only, nothing posted

    review_body = "See the Argus summary comment for the full report."
    try:
        gh.post(gh.repo_path(f"/pulls/{pr_number}/reviews"), {
            "commit_id": head_sha,
            "event": verdict,
            "body": review_body,
            "comments": _inline_comments(findings, config),
        })
    except Exception as e:  # inline line may be outside the diff — retry without inline
        gh.post(gh.repo_path(f"/pulls/{pr_number}/reviews"), {
            "commit_id": head_sha, "event": verdict,
            "body": review_body + f"\n\n_(inline comments skipped: {e})_", "comments": [],
        })

    body = _summary_body(pr, head_sha, verdict, findings, summary, cost_line, trims, state.marker(new_state))
    cid = new_state.get("_comment_id")
    if cid:
        gh.patch(gh.repo_path(f"/issues/comments/{cid}"), {"body": body})
    else:
        gh.post(gh.repo_path(f"/issues/{pr_number}/comments"), {"body": body})
    return verdict


def note_only(pr_number: int, text: str, new_state: dict) -> None:
    """Post/refresh the summary comment with a note (no review event). Used for
    skip / no-material-change / budget-stop / schema-failure paths."""
    if _dry():
        return  # shadow: artifact only
    body = f"## 🛡️ Argus\n\n{text}\n\n{state.marker(new_state)}"
    cid = new_state.get("_comment_id")
    if cid:
        gh.patch(gh.repo_path(f"/issues/comments/{cid}"), {"body": body})
    else:
        gh.post(gh.repo_path(f"/issues/{pr_number}/comments"), {"body": body})
