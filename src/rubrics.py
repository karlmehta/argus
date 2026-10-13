"""Rubric (skill) front-matter parsing + path-aware selection.

A rubric is loaded only when `always: true` or one of its `applies_to` globs matches
a changed file — this is the single biggest fixed-prompt saving vs v1, which loaded
every skill every run. Missing front-matter ⇒ treated as `always: true` (backward
compatible) with a logged warning.
"""
from __future__ import annotations

import os
import sys

import yaml

from . import globs


def parse_rubric(path: str) -> tuple[dict, str]:
    """Return (front_matter_dict, body_markdown)."""
    text = open(path, encoding="utf-8").read()
    meta: dict = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            try:
                meta = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                meta = {}
            body = parts[2]
    return meta, body.strip()


def select_rubrics(skills_dir: str, enabled: list[str], changed_files: list[str]) -> list[dict]:
    """Return selected rubrics sorted by name: [{name, body, reason}]. Sorted for a
    cache-stable prefix (§4.6)."""
    selected: list[dict] = []
    for name in enabled:
        path = os.path.join(skills_dir, f"{name}.md")
        if not os.path.exists(path):
            print(f"::warning::argus: skill '{name}' listed in config but {path} is missing", file=sys.stderr)
            continue
        meta, body = parse_rubric(path)
        if not meta:
            print(f"::warning::argus: skill '{name}' has no front-matter; treating as always-on", file=sys.stderr)
            selected.append({"name": name, "body": body, "reason": "always (no front-matter)"})
            continue
        applies = meta.get("applies_to") or []
        if meta.get("always") is True:
            selected.append({"name": name, "body": body, "reason": "always"})
        elif any(globs.matches_any(f, applies) for f in changed_files):
            hit = next(f for f in changed_files if globs.matches_any(f, applies))
            selected.append({"name": name, "body": body, "reason": f"matched {hit}"})
    selected.sort(key=lambda r: r["name"])
    return selected
