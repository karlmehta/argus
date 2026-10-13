"""Argus v2 orchestrator — deterministic pipeline, 1–2 model calls per run.

Steps: debounce → gate → delta → context pack → budget → triage(Haiku) →
review(Haiku|Sonnet) → merge findings → post → record. The model never uses tools.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
import time

import yaml

from . import context_pack, delta, gate, gh, llm, post, rubrics, state

HARNESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.environ.get("GITHUB_WORKSPACE", ".")


def _read(path: str, default: str = "") -> str:
    try:
        return open(path, encoding="utf-8").read()
    except OSError:
        return default


def load_config() -> dict:
    cfg_path = os.environ.get("ARGUS_CONFIG", ".github/argus/config.yml")
    for p in (os.path.join(WORKSPACE, cfg_path), os.path.join(HARNESS, "config", "argus.yml")):
        if os.path.exists(p):
            return yaml.safe_load(open(p, encoding="utf-8")) or {}
    return {}


def load_memory() -> str:
    """Per-repo memory (isolation guarantee) — from the TARGET repo only."""
    base = os.path.join(WORKSPACE, ".github", "argus", "memory")
    parts = []
    for name in ("conventions.md", "accepted-patterns.md"):
        txt = _read(os.path.join(base, name))
        if txt.strip():
            parts.append(f"## {name}\n{txt.strip()}")
    return "\n\n".join(parts)


def load_event() -> dict:
    return json.load(open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8"))


def resolve_pr(event: dict, event_name: str) -> tuple[dict, bool]:
    """Return (pr_dict, full_review_requested)."""
    full = False
    if event_name == "issue_comment":
        number = event["issue"]["number"]
        pr = gh.get(gh.repo_path(f"/pulls/{number}"))
        full = "--full" in (event.get("comment", {}).get("body", ""))
    else:
        pr = event["pull_request"]
    return pr, full


def record_artifact(data: dict) -> None:
    json.dump(data, open(os.path.join(WORKSPACE, "argus-run.json"), "w"), indent=2)


def merge_findings(new: list[dict], prior: list[dict], resolved_ids: list[str], changed_files: list[str]) -> list[dict]:
    """Carry forward prior findings the model didn't resolve and whose file is untouched;
    dedupe by (file,line,title)."""
    kept_prior = [p for p in prior if p.get("id") not in set(resolved_ids) and p.get("file") not in set(changed_files)]
    merged, seen = [], set()
    for f in new + kept_prior:
        key = (f.get("file"), f.get("line"), f.get("title"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(f)
    return merged


def _fid(f: dict) -> str:
    return hashlib.sha1(f"{f.get('file')}:{f.get('line')}:{f.get('title')}".encode()).hexdigest()[:10]


def main() -> int:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    event = load_event()
    config = load_config()
    if config.get("dry_run") or os.environ.get("ARGUS_DRY_RUN") == "1":
        os.environ["ARGUS_DRY_RUN"] = "1"  # shadow mode: run the pipeline, post nothing
    pr, full = resolve_pr(event, event_name)
    pr_number, head_sha, base_sha = pr["number"], pr["head"]["sha"], pr["base"]["sha"]

    run = {"event": event_name, "pr": pr_number, "head": head_sha, "calls": [], "cost_usd": 0.0}
    st = state.read_state(pr_number)

    # [0] Debounce — superseded synchronize runs make zero model calls.
    if event_name == "pull_request" and event.get("action") == "synchronize":
        time.sleep(int(config.get("debounce_minutes", 10)) * 60)
        latest = gh.get(gh.repo_path(f"/pulls/{pr_number}"))["head"]["sha"]
        if latest != head_sha:
            print(f"superseded by {latest[:8]} — exiting without a model call")
            record_artifact({**run, "result": "superseded"})
            return 0

    # [1] Gate (no LLM)
    rng = delta.resolve_range(base_sha, head_sha, st.get("last_reviewed_sha"), full)
    changed = delta.changed_files(rng)
    g = gate.evaluate(pr, changed, config)
    if g["action"] == "skip":
        post.note_only(pr_number, f"No review needed: {g['reason']}.", {**st, "last_reviewed_sha": head_sha})
        record_artifact({**run, "result": "gated", "reason": g["reason"]})
        return 0

    reviewable = gate.non_skipped(changed, config)
    changed_names = [f["filename"] for f in reviewable]

    # [3] Context pack (no LLM)
    enabled = config.get("skills", []) or [s.replace(".md", "") for s in os.listdir(os.path.join(HARNESS, "skills"))]
    selected = rubrics.select_rubrics(os.path.join(HARNESS, "skills"), enabled, changed_names)
    system_md = _read(os.path.join(HARNESS, "prompts", "system.md"))
    stable_prefix = context_pack.build_stable_prefix(system_md, selected, load_memory())
    suffix, pack_meta = context_pack.build_variable_suffix(pr, reviewable, st.get("findings", []), rng, config)
    run["rubrics"] = [r["name"] for r in selected]
    run["pack"] = pack_meta

    # [4+] Budgets
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    budget = config.get("budget", {})
    daily = state.read_daily_spend(today)
    if budget.get("per_repo_daily_usd") and daily >= budget["per_repo_daily_usd"]:
        post.note_only(pr_number, f"Argus paused: repo daily budget ${budget['per_repo_daily_usd']} reached (${daily:.2f}).", {**st, "last_reviewed_sha": st.get("last_reviewed_sha")})
        record_artifact({**run, "result": "daily_budget_stop"})
        return 0
    if budget.get("per_pr_usd") and st.get("spend_usd", 0.0) >= budget["per_pr_usd"]:
        post.note_only(pr_number, f"Argus: per-PR budget ${budget['per_pr_usd']} reached — summary-only. Ask a human to review.", st)
        record_artifact({**run, "result": "pr_budget_stop"})
        return 0

    models = config.get("models", {})
    triage_model = models.get("triage", "claude-haiku-4-5")

    def track(model: str, usage: dict, kind: str) -> None:
        c = llm.cost_usd(model, usage)
        run["cost_usd"] = round(run["cost_usd"] + c, 6)
        run["calls"].append({"kind": kind, "model": model, "usage": usage, "cost_usd": c})

    # Summary-only mode for oversized PRs: one Haiku summary, no deep review.
    if g["action"] == "summary_only":
        obj, usage = llm.call_json(triage_model, stable_prefix, suffix,
                                   "This PR is too large to deep-review. Return a review object with an empty findings list and a summary naming the highest-risk files and asking for a split.",
                                   REVIEW_SCHEMA, "review", 1200)
        track(triage_model, usage, "summary_only")
        _finish(pr, head_sha, [], obj.get("summary", g.get("note", "")), config, st, changed_names, [], run, today)
        return 0

    # [4] Triage
    pre = llm.count_input_tokens(triage_model, stable_prefix, suffix, "triage")
    run["pack"]["counted_input_tokens"] = pre
    if budget.get("per_run_usd"):
        est = llm.cost_usd(triage_model, {"input_tokens": pre, "output_tokens": 4000})
        if est > budget["per_run_usd"]:
            post.note_only(pr_number, f"Argus: estimated run cost ${est:.2f} exceeds per-run budget ${budget['per_run_usd']}. Split the PR or raise the budget.", st)
            record_artifact({**run, "result": "per_run_budget_stop"})
            return 0

    triage, usage = llm.call_json(triage_model, stable_prefix, suffix, _read(os.path.join(HARNESS, "prompts", "triage.md")),
                                  TRIAGE_SCHEMA, "triage", 1000)
    track(triage_model, usage, "triage")
    run["triage"] = triage

    if triage.get("trivial"):
        post.note_only(pr_number, f"No material change since `{(st.get('last_reviewed_sha') or base_sha)[:8]}` — previous verdict stands. ({triage.get('reason','')})",
                       {**st, "last_reviewed_sha": head_sha})
        record_artifact({**run, "result": "trivial"})
        return 0

    # [4b] Review — model + scope by risk
    risk = triage.get("risk", "medium")
    strict = config.get("strict_globs", []) or config.get("paths", {}).get("strict", [])
    force_high = any(gate.globs.matches_any(n, strict) for n in changed_names) if strict else False
    if risk == "high" or force_high:
        review_model = models.get("review_high_risk", "claude-sonnet-4-6")
        deep = triage.get("files_for_deep_review") or changed_names
        deep_files = [f for f in reviewable if f["filename"] in set(deep)] or reviewable
        suffix, pack_meta = context_pack.build_variable_suffix(pr, deep_files, st.get("findings", []), rng, config)
    else:
        review_model = models.get("review_default", "claude-haiku-4-5")

    review_obj, usage = llm.call_json(review_model, stable_prefix, suffix, _read(os.path.join(HARNESS, "prompts", "review.md")),
                                      REVIEW_SCHEMA, "review", 4000)
    track(review_model, usage, f"review:{risk}")

    # [5] Merge + confidence filter
    min_conf = config.get("min_confidence", 0.6)
    findings = []
    for f in review_obj.get("findings", []):
        f["id"] = f.get("id") or _fid(f)
        if f.get("severity") == "blocker" or f.get("confidence", 1.0) >= min_conf:
            findings.append(f)
    findings = merge_findings(findings, st.get("findings", []), review_obj.get("resolved_prior_ids", []), changed_names)

    _finish(pr, head_sha, findings, review_obj.get("summary", ""), config, st, changed_names, pack_meta.get("trims", []), run, today)
    return 0


def _finish(pr, head_sha, findings, summary, config, st, changed_names, trims, run, today) -> None:
    new_spend = round(st.get("spend_usd", 0.0) + run["cost_usd"], 6)
    new_state = {"version": 2, "last_reviewed_sha": head_sha, "findings": findings,
                 "spend_usd": new_spend, "_comment_id": st.get("_comment_id")}
    cached = sum(c["usage"].get("cache_read_input_tokens", 0) for c in run["calls"])
    inp = sum(c["usage"].get("input_tokens", 0) + c["usage"].get("cache_read_input_tokens", 0) + c["usage"].get("cache_creation_input_tokens", 0) for c in run["calls"])
    out = sum(c["usage"].get("output_tokens", 0) for c in run["calls"])
    pct = int(100 * cached / inp) if inp else 0
    cost_line = f"~${run['cost_usd']:.3f} · {inp//1000}k in / {out//1000}k out · {pct}% cached · {len(run['calls'])} call(s)"
    verdict = post.publish(pr, head_sha, findings, summary, config, new_state, cost_line, trims)
    run["verdict"] = verdict
    state.add_daily_spend(today, run["cost_usd"])
    record_artifact({**run, "result": "reviewed", "spend_pr_usd": new_spend, "findings": findings})


# Schemas loaded at import (also written to schemas/ for the workflow artifact).
TRIAGE_SCHEMA = json.load(open(os.path.join(HARNESS, "schemas", "triage.json")))
REVIEW_SCHEMA = json.load(open(os.path.join(HARNESS, "schemas", "review.json")))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print(f"::error::argus failed: {e}")
        raise
