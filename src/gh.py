"""Thin GitHub REST client (no LLM). Reads token + repo from the Actions env.

Kept deliberately small — Argus v2 only needs: read PR + comments, create/edit
one summary comment, and submit a review bound to a commit_id.
"""
from __future__ import annotations

import os
from typing import Any

import requests

API = "https://api.github.com"


def _token() -> str:
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not tok:
        raise RuntimeError("GH_TOKEN / GITHUB_TOKEN not set")
    return tok


def _repo() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY not set")
    return repo


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request(method: str, path: str, **kw) -> requests.Response:
    url = path if path.startswith("http") else f"{API}{path}"
    r = requests.request(method, url, headers=_headers(), timeout=30, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub {method} {path} -> {r.status_code}: {r.text[:400]}")
    return r


def get(path: str, **kw) -> Any:
    return _request("GET", path, **kw).json()


def paginate(path: str, **kw) -> list[dict]:
    """Follow Link headers; return all items."""
    out: list[dict] = []
    url = path if path.startswith("http") else f"{API}{path}"
    while url:
        r = _request("GET", url, **kw)
        out.extend(r.json())
        url = r.links.get("next", {}).get("url")
        kw.pop("params", None)  # params only on first page
    return out


def post(path: str, body: dict) -> Any:
    return _request("POST", path, json=body).json()


def patch(path: str, body: dict) -> Any:
    return _request("PATCH", path, json=body).json()


def put(path: str, body: dict) -> Any:
    return _request("PUT", path, json=body).json()


def repo_path(suffix: str) -> str:
    return f"/repos/{_repo()}{suffix}"
