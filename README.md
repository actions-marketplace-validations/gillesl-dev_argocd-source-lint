# argocd-source-lint

[![Tests](https://github.com/gillesl-dev/argocd-source-lint/actions/workflows/test.yml/badge.svg)](https://github.com/gillesl-dev/argocd-source-lint/actions/workflows/test.yml)

Static linter to detect silent failures in multi-source ArgoCD
`Application` resources: resources never synced, broken `$values`,
missing `ignoreDifferences`, phantom targets.

Analyzes the Git repo it runs in (the checkout already present in CI) —
no cluster access, no `kubeconfig`, no sensitive data involved.

## What the tool does

- `orphan-source` — a manifest present in the repo but not covered by any
  declared source.
- `broken-values-ref` — a `$ref` in a Helm `valueFiles` entry with no
  matching source or file.
- `missing-ignore-diff` — a known at-risk CRD (CNPG, cert-manager...) with
  no `ignoreDifferences` while `selfHeal: true` is active.
- `phantom-target` — a `targetRevision`/`path` that resolves to nothing in
  the repo.
- `unresolvable-generator` — an `ApplicationSet` generator this tool can't
  resolve from a local checkout alone (live cluster/API access, or
  `goTemplate: true` rendering).

## What the tool does not do (v1)

- No cluster access.
- No Kustomize *rendering* (bases merged, patches applied) — delegate to
  `kustomize build`/a dedicated linter for that. `orphan-source` does
  read `kustomization.yaml`'s `resources`/`bases`/`components`/`patches`/
  generators to know which files in the overlay are actually referenced,
  the same signal as a plain directory source (see DESIGN.md); a remote
  resource reference is silently skipped, not guessed at.
- `ApplicationSet` support covers `list`, `git` (`directories`/`files`)
  and `matrix` generators — each generated `Application` goes through
  the same rules as a plain one. `clusters`/`scmProvider`/`pullRequest`/
  `merge`/`plugin` generators and `goTemplate: true` rendering require
  live cluster/API access or a different templating engine — out of
  scope v1, flagged `unresolvable-generator` rather than guessed at.
- Multi-repo `Application` resources (sources pointing to a repo other
  than the one analyzed) are detected and flagged `info`, never checked
  nor silently ignored.

## Installation

```bash
pip install argocd-source-lint
```

## Usage

```bash
# From the root of the repo to analyze
argocd-source-lint .

# Output formats: table (default), json, sarif, gitlab-codequality
argocd-source-lint . --format sarif --output results.sarif
```

Exit code: `0` if no blocking finding, `1` otherwise. An `error` finding
always blocks; an `unverifiable` one (e.g. a Git revision not locally
resolvable — incomplete shallow clone) blocks by default, configurable via
`unverifiable_blocks_ci`.

## Configuration

Copy [`.argocd-lint.example.yaml`](./.argocd-lint.example.yaml) to
`.argocd-lint.yaml` at the root of the repo to analyze. Any omitted key
keeps its default value:

```yaml
scan_roots:
  - manifests/
  - infra/

rules:
  orphan-source: error
  broken-values-ref: error
  missing-ignore-diff: warning
  phantom-target: error
  unresolvable-generator: info

unverifiable_blocks_ci: true

exclude_paths:
  - manifests/legacy/**

# Additional operator signatures, on top of the built-in pack
# (CNPG, cert-manager) — never a replacement.
known_operators:
  - crd_trigger: my-operator.io/MyCRD
    name_from: metadata.name
    expect_ignore_on:
      - kind: Secret
        name_pattern: "{name}-credentials"
```

## Adopting on an existing repo

A first run on a large, existing repo will likely surface pre-existing
issues (a decommissioned component never archived, a manifest applied
out-of-band). Accept them once so only *new* findings block CI from now
on:

```bash
argocd-source-lint . --write-baseline
```

This writes `.argocd-lint-baseline.yaml` — commit it. It's plain YAML
(rule, file, application, message), meant to be reviewed like any other
file, not a hash lockfile. Re-run `--write-baseline` any time you want to
accept the current state again (it overwrites the file outright).

## CI/CD integration

### GitHub Actions

```yaml
- uses: gillesl-dev/argocd-source-lint@v0.1.6
  with:
    path: .
```

### GitLab CI

```yaml
include:
  - component: $CI_SERVER_FQDN/<namespace>/argocd-source-lint/lint@v0.1.6
    inputs:
      scope: manifests/
```

### pre-commit

```yaml
repos:
  - repo: https://github.com/gillesl-dev/argocd-source-lint
    rev: v0.1.6
    hooks:
      - id: argocd-source-lint
```

## Development

```bash
uv sync --extra dev
uv run argocd-source-lint .
uv run pytest
```

See [DESIGN.md](./DESIGN.md) for the reasoning behind the mono-repo v1
scope, the `directory.recurse`/`include`/`exclude` semantics, and other
non-obvious decisions, and [CONTRIBUTING.md](./CONTRIBUTING.md) to add a
rule or an operator signature.

## License

MIT — see [LICENSE](./LICENSE).
