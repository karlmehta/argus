---
name: security
always: false
applies_to: ["**/auth/**", "**/payments/**", "**/billing/**", "**/*.sql", "**/middleware/**", "**/*secret*", "**/*token*", "**/*password*", "**/*permission*", "**/*tenant*", "**/*crypto*", "**/*oauth*"]
---

# Skill: security

Find ways this change lets someone do something they shouldn't. Read auth and
data-access paths especially closely.

## Checklist
- **AuthN/AuthZ:** Does every new endpoint/handler declare a permission? Is the
  object-level check present (not just "is logged in")? A view that loads a record
  by id without scoping to the caller's org/user is an **IDOR** → `blocker`.
- **Tenant / org scoping:** In multi-tenant code, every query on shared tables must
  filter by tenant/org. A missing scope that can return another tenant's rows is a
  `blocker`.
- **Injection:** Raw SQL built with string interpolation, shell commands from user
  input, template rendering of untrusted strings, `eval`/`exec`, unsafe
  deserialization (`pickle`, `yaml.load`, `Marshal`) → `blocker`/`major`.
- **SSRF:** User-controlled URLs passed to server-side fetchers without an
  allow-list → `major`+.
- **Secrets:** Any credential, token, private key, or connection string added to
  code, tests, or fixtures → `blocker`. Also flag secrets logged or returned in API
  responses.
- **Output/rendering:** Untrusted input reaching HTML/JS/email bodies without
  escaping (XSS), or reflected into logs enabling log injection.
- **Crypto & tokens:** Predictable tokens, weak randomness (`Math.random`,
  `random`) for security values, missing constant-time compare, tokens without
  expiry.
- **File & path:** Path traversal from user input, unrestricted upload types,
  writing to attacker-controlled paths.
- **Auth boundaries:** Privilege checks that trust client-supplied role/ids;
  mutations reachable without CSRF protection where relevant.

## Severity guidance
Data exfiltration, auth bypass, RCE, secret exposure → `blocker`. Hardening gaps
with a plausible-but-narrow exploit → `major`. Defense-in-depth suggestions →
`minor`. In `strict:` paths, drop one threshold lower.

## Don't
Don't flag a missing scope you haven't confirmed — read the queryset/manager; the
scope may be applied by a base class or middleware. Say "confirm X" as a *question*
if you can't verify.
