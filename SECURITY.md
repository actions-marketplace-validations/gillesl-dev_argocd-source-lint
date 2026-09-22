# Security policy

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repo:
https://github.com/gillesl-dev/argocd-source-lint/security/advisories/new

Don't open a public issue for a vulnerability report — the advisory
flow above is private until a fix ships.

## Supported versions

Only the latest tagged release. This is a young, actively-developed
tool (pre-1.0) — there's no LTS branch to backport a fix to.

## Trust model

This tool treats the Git repo it runs against as **untrusted input**,
not just data to display back. In a real CI job that repo can contain
a PR from a fork, so every string that ends up in an `Application`,
`ApplicationSet`, or `AppProject` manifest — a path, a revision, a
glob pattern, a name — is adversarial until proven otherwise, not just
malformed-by-accident.

Concretely, that means:
- No filesystem path built from repo content may resolve outside the
  repo (or a materialized revision snapshot) it's supposed to be
  bounded to.
- No string built from repo content is ever passed to `git` (or any
  other subprocess) in a way that could be read as a flag instead of
  data.
- No repo-controlled string is fed to a regex engine, or any other
  algorithm, whose worst-case cost isn't bounded independently of how
  adversarial the input is.
- No repo-controlled string is trusted as markup/HTML/XML when
  rendering a report — it's data, escaped like any other.

See [DESIGN.md](./DESIGN.md) for the specific issues this caught in
practice (each one confirmed by actually triggering it, not just
reasoning about it) and how each was fixed.

One inherent limitation, not a code defect: `.argocd-lint.yaml` and
`.argocd-lint-baseline.yaml` are themselves repo content. A PR that
introduces an issue can, in the same PR, downgrade the rule that would
catch it or add a baseline entry suppressing it — the same class of
thing as a `# noqa` comment or an `.eslintrc` change in any other
linter, and not something a code change in this tool can close. If
you run this against untrusted forks' PRs, protect both files with
`CODEOWNERS` or branch protection, the same way you'd protect your CI
configuration itself.

## Out of scope

- Findings about the *content* of a repo this tool is pointed at
  (a real misconfiguration it correctly reports) — that's the whole
  point of the tool, not a vulnerability in it.
- Denial of service from a legitimately huge repo with no adversarial
  intent (the repo owner controls what's in their own repo).
