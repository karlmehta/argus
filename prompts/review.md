# Review

Review the delta against the loaded rubrics. Return the `review` tool object only.

For each real problem, emit a finding with: `skill` (which rubric), `severity`,
`file` + `line` (in the new/HEAD file, as shown in the context windows), a short
`title`, a `body` of ≤80 words that states the problem and a concrete fix, and a
`confidence` in 0.0–1.0.

Rules:
- Only flag what the provided context supports. If you'd need to see another file
  to be sure, lower `confidence` (or omit). Blockers must be certain.
- Do not re-flag anything described in the repository memory.
- If prior unresolved findings are listed and the current code fixes them, put
  their ids in `resolved_prior_ids`.
- Nits go in the object but will be summarized, not posted inline — keep them few.
- `summary`: ≤120 words, the reviewer's bottom line.
- `memory_suggestions`: optional; a convention worth recording for next time.

If the delta is clean, return an empty `findings` list and say so in one line.
