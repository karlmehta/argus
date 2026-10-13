#!/usr/bin/env python3
"""Export merged PRs as replay fixtures (spec §9).

For a repo, pulls the last N merged PRs and records, per PR: base/head SHA, title,
body, changed files, and the v1 findings Argus/Claude previously posted (parsed from
`argus[bot]` / `claude[bot]` reviews). Written to tests/fixtures/prs/<repo>-<n>.json.

Usage:
  gh auth login   # needs repo read
  python tools/export_fixtures.py xspan-ai/xspan-api --count 15 --with-blockers 3
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess

SEV_RE = re.compile(r"\b(blocker|major|minor|nit)\b", re.I)
LOC_RE = re.compile(r"([\w./-]+\.\w+):(\d+)")
BOT_AUTHORS = {"argus", "claude"}


def gh_json(*args: str):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout
    return json.loads(out) if out.strip() else None


def parse_v1_findings(repo: str, number: int) -> list[dict]:
    """Best-effort: scan review + comment bodies from the bot for sev + file:line."""
    findings = []
    reviews = gh_json("api", f"/repos/{repo}/pulls/{number}/reviews", "--paginate") or []
    comments = gh_json("api", f"/repos/{repo}/pulls/{number}/comments", "--paginate") or []
    for item in reviews + comments:
        login = (item.get("user") or {}).get("login", "").replace("[bot]", "")
        if login not in BOT_AUTHORS:
            continue
        body = item.get("body") or ""
        path, line = item.get("path"), item.get("line")
        for m in SEV_RE.finditer(body):
            sev = m.group(1).lower()
            loc = LOC_RE.search(body)
            findings.append({
                "severity": sev,
                "file": path or (loc.group(1) if loc else None),
                "line": line or (int(loc.group(2)) if loc else None),
            })
    return findings


def export(repo: str, count: int, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    prs = gh_json("pr", "list", "--repo", repo, "--state", "merged", "--limit", str(count),
                  "--json", "number,title,body,headRefOid,baseRefOid") or []
    for pr in prs:
        n = pr["number"]
        files = gh_json("api", f"/repos/{repo}/pulls/{n}/files", "--paginate") or []
        fixture = {
            "repo": repo,
            "number": n,
            "title": pr["title"],
            "body": pr.get("body") or "",
            "base_sha": pr["baseRefOid"],
            "head_sha": pr["headRefOid"],
            "changed_files": [{"filename": f["filename"], "additions": f.get("additions", 0),
                               "deletions": f.get("deletions", 0), "status": f.get("status", "modified")[:1].upper()}
                              for f in files],
            "v1_findings": parse_v1_findings(repo, n),
        }
        slug = repo.split("/")[-1]
        path = os.path.join(out_dir, f"{slug}-{n}.json")
        json.dump(fixture, open(path, "w"), indent=2)
        print(f"wrote {path}  ({len(fixture['changed_files'])} files, {len(fixture['v1_findings'])} v1 findings)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", help="owner/name")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--out", default="tests/fixtures/prs")
    a = ap.parse_args()
    export(a.repo, a.count, a.out)
