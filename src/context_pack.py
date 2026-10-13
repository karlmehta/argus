"""Deterministic context-pack builder (no LLM).

Produces a cache-stable STABLE PREFIX (system + selected rubrics + repo memory) and a
per-run VARIABLE SUFFIX (PR meta, prior findings, diff hunks, ±N context windows,
bounded symbol signatures). Enforces a hard token budget by trimming in a fixed,
announced order — never silently.
"""
from __future__ import annotations

import re

from . import delta

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
# Language-agnostic definition pattern (string template; {name} filled per symbol).
DEF_TMPL = (
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|func|interface|type|struct|"
    r"const|let|var|public|private|protected|static)\b.*\b{name}\b"
)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _hunk_new_ranges(diff_text: str) -> list[tuple[int, int]]:
    ranges = []
    for line in diff_text.splitlines():
        m = HUNK_RE.match(line)
        if m:
            start = int(m.group(1))
            count = int(m.group(2) or 1)
            ranges.append((start, max(count, 1)))
    return ranges


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    intervals = sorted(intervals)
    out = [list(intervals[0])]
    for s, e in intervals[1:]:
        if s <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def _context_windows(path: str, diff_text: str, context: int) -> str:
    lines = delta.head_file_lines(path)
    if not lines:
        return ""
    windows = [(max(1, s - context), min(len(lines), s + c - 1 + context)) for s, c in _hunk_new_ranges(diff_text)]
    out = []
    for s, e in _merge(windows):
        body = "\n".join(f"{i:>5}  {lines[i - 1]}" for i in range(s, e + 1))
        out.append(f"--- {path} lines {s}-{e} ---\n{body}")
    return "\n".join(out)


def _symbol_signatures(changed_files: list[dict], diffs: dict[str, str], cap: int) -> str:
    # Identifiers introduced on added (+) lines.
    idents: set[str] = set()
    for d in diffs.values():
        for line in d.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                idents.update(IDENT_RE.findall(line[1:]))
    snippets: list[str] = []
    seen: set[str] = set()
    for f in changed_files:
        if len(snippets) >= cap:
            break
        lines = delta.head_file_lines(f["filename"])
        for i, line in enumerate(lines):
            if len(snippets) >= cap:
                break
            for name in idents:
                key = f"{f['filename']}:{name}"
                if key in seen:
                    continue
                if re.match(DEF_TMPL.format(name=re.escape(name)), line):
                    sig = line.strip()
                    doc = lines[i + 1].strip() if i + 1 < len(lines) and lines[i + 1].strip().startswith(('"""', "'''", "//", "#", "/*", "*")) else ""
                    snippets.append(f"{f['filename']}: {sig}" + (f"  ⏷ {doc}" if doc else ""))
                    seen.add(key)
    return "\n".join(snippets)


def build_stable_prefix(system_md: str, rubrics: list[dict], memory: str) -> str:
    parts = [system_md.strip(), ""]
    parts.append("# Review rubrics (only those relevant to the changed paths)\n")
    for r in rubrics:
        parts.append(f"## Rubric: {r['name']}\n{r['body']}\n")
    if memory.strip():
        parts.append("# Repository memory (intentional patterns — do not re-flag)\n")
        parts.append(memory.strip())
    return "\n".join(parts).strip()


def build_variable_suffix(pr: dict, changed_files: list[dict], prior_findings: list[dict],
                          rng: dict, config: dict) -> tuple[str, dict]:
    context_lines = config.get("context_lines", 30)
    max_symbols = config.get("max_symbol_snippets", 20)
    max_tokens = config.get("max_input_tokens", 60000)

    diffs = {f["filename"]: delta.file_diff(rng, f["filename"], context=0) for f in changed_files}

    header = [
        f"# Pull request #{pr['number']}: {pr.get('title','')}",
        f"Review range: {rng['start'][:8]}..{rng['end'][:8]} ({rng['mode']})",
        "",
        "## Changed files",
        *[f"- {f['status']} {f['filename']} (+{f['additions']}/-{f['deletions']})" for f in changed_files],
        "",
    ]
    body = (pr.get("body") or "").strip()
    if body:
        header += ["## PR description", body[:2000], ""]
    if prior_findings:
        header += ["## Prior unresolved findings (confirm still valid, or mark resolved by id)",
                   *[f"- [{p.get('id')}] {p.get('severity')} {p.get('file')}:{p.get('line')} — {p.get('title')}" for p in prior_findings],
                   ""]

    diff_section = ["## Diff (delta hunks)"]
    for f in changed_files:
        if diffs[f["filename"]].strip():
            diff_section.append(f"### {f['filename']}\n```diff\n{diffs[f['filename']]}\n```")

    ctx = config.get("_ctx", context_lines)
    context_section = ["## Code context (±%d lines around changes, from HEAD)" % ctx]
    for f in changed_files:
        w = _context_windows(f["filename"], diffs[f["filename"]], ctx)
        if w:
            context_section.append(w)

    symbols = _symbol_signatures(changed_files, diffs, max_symbols)
    symbol_section = ["## Referenced symbol signatures", symbols] if symbols else []

    def assemble(sections: list[list[str]]) -> str:
        return "\n".join("\n".join(s) for s in sections if s).strip()

    meta = {"files_included": [f["filename"] for f in changed_files], "files_trimmed": [], "trims": []}

    # Budget trim: symbols → shrink context to 10 → drop lowest-priority files (by churn).
    order = [header, diff_section, context_section, symbol_section]
    suffix = assemble(order)
    if estimate_tokens(suffix) > max_tokens and symbol_section:
        symbol_section = []
        meta["trims"].append("dropped symbol signatures")
        suffix = assemble([header, diff_section, context_section, symbol_section])
    if estimate_tokens(suffix) > max_tokens:
        context_section = ["## Code context (±10 lines around changes, from HEAD)"]
        for f in changed_files:
            w = _context_windows(f["filename"], diffs[f["filename"]], 10)
            if w:
                context_section.append(w)
        meta["trims"].append("shrank context windows to ±10")
        suffix = assemble([header, diff_section, context_section, symbol_section])
    if estimate_tokens(suffix) > max_tokens:
        ranked = sorted(changed_files, key=lambda f: f["additions"] + f["deletions"])
        kept = changed_files
        while estimate_tokens(suffix) > max_tokens and len(kept) > 1:
            drop = ranked.pop(0)
            if drop in kept:
                kept = [f for f in kept if f is not drop]
                meta["files_trimmed"].append(drop["filename"])
            diff_section = ["## Diff (delta hunks)"]
            context_section = ["## Code context (from HEAD)"]
            for f in kept:
                if diffs[f["filename"]].strip():
                    diff_section.append(f"### {f['filename']}\n```diff\n{diffs[f['filename']]}\n```")
                w = _context_windows(f["filename"], diffs[f["filename"]], 10)
                if w:
                    context_section.append(w)
            suffix = assemble([header, diff_section, context_section, symbol_section])
        if meta["files_trimmed"]:
            meta["trims"].append(f"dropped {len(meta['files_trimmed'])} low-churn files from deep context")

    meta["est_input_tokens"] = estimate_tokens(suffix)
    return suffix, meta
