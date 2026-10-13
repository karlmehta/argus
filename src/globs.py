"""Path-glob matching for file paths. `**` matches across directory separators;
`*` matches within a path segment. Used for skip/strict/applies_to globs."""
from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern:
    i, n, out = 0, len(pattern), []
    while i < n:
        c = pattern[i]
        if pattern.startswith("**", i):
            # ** = any chars incl. '/'. Swallow a following '/' so **/x also matches x.
            if pattern.startswith("**/", i):
                out.append("(?:.*/)?")
                i += 3
            else:
                out.append(".*")
                i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches(path: str, pattern: str) -> bool:
    return _compile(pattern).match(path) is not None


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(matches(path, p) for p in patterns or [])
