"""Offline unit tests for the deterministic parts of the Argus v2 pipeline
(no network, no model calls). Run: `python -m pytest tests/` (PyYAML required)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import context_pack, gate, globs, rubrics  # noqa: E402

SKILLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")


def test_globs():
    assert globs.matches("apps/auth/views.py", "**/auth/**")
    assert globs.matches("x.sql", "**/*.sql")
    assert globs.matches("a/b/c.py", "**/*.py")
    assert not globs.matches("apps/authx/v.py", "**/auth/**")
    assert globs.matches_any("pkg/payments/charge.ts", ["**/billing/**", "**/payments/**"])


def test_gate_skips():
    f = [{"filename": "a.py", "additions": 1, "deletions": 0}]
    assert gate.evaluate({"draft": True, "user": {"login": "x"}}, f, {})["action"] == "skip"
    assert gate.evaluate({"user": {"login": "dependabot[bot]"}}, f, {})["action"] == "skip"
    lock = [{"filename": "poetry.lock", "additions": 9, "deletions": 9}]
    assert gate.evaluate({"user": {"login": "k"}}, lock, {})["action"] == "skip"


def test_gate_size_and_proceed():
    big = [{"filename": "a.py", "additions": 900, "deletions": 0}]
    assert gate.evaluate({"user": {"login": "k"}}, big, {"max_changed_lines": 800})["action"] == "summary_only"
    ok = [{"filename": "a.py", "additions": 5, "deletions": 0}]
    assert gate.evaluate({"user": {"login": "k"}}, ok, {})["action"] == "proceed"


def test_rubric_path_selection():
    always = [r["name"] for r in rubrics.select_rubrics(SKILLS, ["correctness", "security"], ["apps/foo/bar.py"])]
    assert "correctness" in always and "security" not in always
    on_auth = [r["name"] for r in rubrics.select_rubrics(SKILLS, ["correctness", "security"], ["apps/auth/login.py"])]
    assert "security" in on_auth
    on_lock = [r["name"] for r in rubrics.select_rubrics(SKILLS, ["dependencies"], ["poetry.lock"])]
    assert "dependencies" in on_lock


def test_rubrics_sorted_for_cache_stability():
    names = [r["name"] for r in rubrics.select_rubrics(SKILLS, ["tests", "correctness"], ["x.py"])]
    assert names == sorted(names)


def test_hunk_parsing_and_merge():
    assert context_pack._hunk_new_ranges("@@ -1,2 +10,5 @@\n+x\n@@ -20 +30 @@\n+y") == [(10, 5), (30, 1)]
    assert context_pack._merge([(1, 5), (4, 8), (20, 22)]) == [(1, 8), (20, 22)]


def test_token_estimate_monotonic():
    assert context_pack.estimate_tokens("x" * 400) == 100
