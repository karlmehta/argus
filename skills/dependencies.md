---
name: dependencies
always: false
applies_to: ["**/requirements*.txt", "**/package.json", "**/go.mod", "**/go.sum", "**/Cargo.toml", "**/pyproject.toml", "**/Gemfile", "**/*.lock", "**/poetry.lock", "**/pnpm-lock.yaml"]
---

# Skill: dependencies

Review what the PR pulls into the tree. New dependencies are permanent liabilities.

## Checklist
- **Necessity:** does this dep earn its place, or does it replace ~20 lines of
  first-party code? Micro-deps and one-function packages are a supply-chain and
  maintenance cost.
- **Provenance & health:** obscure/unmaintained package, very low downloads, recent
  ownership change, typosquat-looking name, no source repo. Flag for a human to vet.
- **License:** copyleft (GPL/AGPL) or non-OSI license pulled into a proprietary
  codebase → `blocker` until legal-checked. Missing/unknown license → `major`.
- **Pinning & integrity:** unpinned version ranges on a new critical dep; lockfile
  not updated; missing hashes/integrity where the ecosystem supports them.
- **Transitive blast radius:** a dep that drags in a large or risky transitive tree;
  native build steps; postinstall scripts (npm) → supply-chain smell.
- **Duplication:** adds a second library that does what an existing one already does
  (two HTTP clients, two date libs) → fragmentation.
- **Version bumps:** major-version bump of an existing dep without noting breaking
  changes; a bump that isn't reflected in the lockfile.

## Severity guidance
Risky license or clear supply-chain red flag → `blocker`/`major` (route to a human).
Unpinned or duplicative dep → `minor`. Prefer "vet before merge" language over hard
assertions you can't verify from the diff.
