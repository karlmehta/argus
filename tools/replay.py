#!/usr/bin/env python3
"""Replay fixtures through the REAL v2 pipeline (dry-run) and score cost + recall.

For each fixture it clones (once) + checks out the PR head, synthesizes a
`pull_request` event, runs `python -m src.main` with ARGUS_DRY_RUN=1, and reads
argus-run.json. Reports total/per-PR v2 cost and blocker/major recall vs the
fixture's v1 findings (file match within ±line_tol). v1 cost comes from the
Anthropic Console for the same dates/key — not computable here.

Usage:
  export ANTHROPIC_API_KEY=sk-...      # dedicated argus key
  python tools/replay.py --fixtures tests/fixtures/prs --work /tmp/argus-replay
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys

HARNESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE_TOL = 8


def _run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def ensure_clone(repo: str, work: str) -> str:
    dest = os.path.join(work, repo.replace("/", "__"))
    if not os.path.isdir(os.path.join(dest, ".git")):
        os.makedirs(work, exist_ok=True)
        r = _run(["gh", "repo", "clone", repo, dest, "--", "--no-single-branch"])
        if r.returncode:
            raise RuntimeError(f"clone {repo} failed: {r.stderr[:300]}")
    return dest


def replay_one(fx: dict, work: str) -> dict | None:
    repo, n = fx["repo"], fx["number"]
    clone = ensure_clone(repo, work)
    if _run(["git", "fetch", "--all", "--quiet"], cwd=clone).returncode == 0:
        pass
    if _run(["git", "checkout", "--quiet", fx["head_sha"]], cwd=clone).returncode != 0:
        print(f"  skip {repo}#{n}: head {fx['head_sha'][:8]} not fetchable")
        return None

    event = {
        "action": "opened",
        "pull_request": {
            "number": n, "title": fx["title"], "body": fx["body"], "draft": False,
            "user": {"login": "replay"},
            "head": {"sha": fx["head_sha"]}, "base": {"sha": fx["base_sha"]},
        },
    }
    event_path = os.path.join(work, "event.json")
    json.dump(event, open(event_path, "w"))

    env = {**os.environ,
           "GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": event_path,
           "GITHUB_WORKSPACE": clone, "GITHUB_REPOSITORY": repo,
           "ARGUS_DRY_RUN": "1", "ARGUS_CONFIG": ".github/argus/config.yml",
           "GH_TOKEN": os.environ.get("GH_TOKEN", "")}
    # state marker read hits GitHub; dry-run still reads it. For a clean first-review
    # replay, point at a PR with no prior Argus comment, or accept incremental ranges.
    r = _run([sys.executable, "-m", "src.main"], cwd=HARNESS, env=env)
    art = os.path.join(clone, "argus-run.json")
    if not os.path.exists(art):
        print(f"  {repo}#{n}: no artifact. stderr: {r.stderr[-300:]}")
        return None
    run = json.load(open(art))
    run["v1_findings"] = fx.get("v1_findings", [])
    return run


def recall(v2: list[dict], v1: list[dict]) -> tuple[int, int]:
    """Blocker/major recall: how many v1 blocker/major locations v2 also flagged
    (same file, line within ±LINE_TOL)."""
    v1b = [f for f in v1 if f.get("severity") in ("blocker", "major") and f.get("file")]
    v2b = [f for f in v2 if f.get("severity") in ("blocker", "major") and f.get("file")]
    hit = 0
    for a in v1b:
        for b in v2b:
            if a["file"] == b.get("file") and (a.get("line") is None or b.get("line") is None
                                               or abs((a["line"] or 0) - (b.get("line") or 0)) <= LINE_TOL):
                hit += 1
                break
    return hit, len(v1b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", default="tests/fixtures/prs")
    ap.add_argument("--work", default="/tmp/argus-replay")
    a = ap.parse_args()

    results, tot_cost, tot_hit, tot_v1 = [], 0.0, 0, 0
    for path in sorted(glob.glob(os.path.join(a.fixtures, "*.json"))):
        fx = json.load(open(path))
        run = replay_one(fx, a.work)
        if not run:
            continue
        v2_findings = run.get("findings", [])
        hit, n1 = recall(v2_findings, run["v1_findings"])
        tot_cost += run.get("cost_usd", 0.0); tot_hit += hit; tot_v1 += n1
        results.append({"pr": f"{fx['repo']}#{fx['number']}", "cost_usd": round(run.get("cost_usd", 0.0), 4),
                        "result": run.get("result"), "v2_blk_maj": len([f for f in v2_findings if f.get("severity") in ("blocker", "major")]),
                        "v1_blk_maj": n1, "recall_hits": hit})
        print(f"  {fx['repo']}#{fx['number']}: ${run.get('cost_usd',0):.4f} {run.get('result')} recall {hit}/{n1}")

    print("\n=== Replay report ===")
    print(f"PRs replayed: {len(results)}")
    print(f"v2 total cost: ${tot_cost:.2f}  ·  avg/PR: ${tot_cost/max(len(results),1):.4f}")
    print(f"blocker/major recall: {tot_hit}/{tot_v1} = {(100*tot_hit/tot_v1) if tot_v1 else 0:.0f}%")
    print("(v1 cost: read the Anthropic Console for the same dates/key — not computable offline.)")
    json.dump({"results": results, "v2_total_cost": round(tot_cost, 4),
               "recall": {"hits": tot_hit, "v1_total": tot_v1}},
              open("replay-report.json", "w"), indent=2)
    print("wrote replay-report.json")


if __name__ == "__main__":
    main()
