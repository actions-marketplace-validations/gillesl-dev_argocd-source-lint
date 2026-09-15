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

## What the tool does not do (v1)

- No cluster access.
- No native Kustomize coverage (a directory with `kustomization.yaml` is
  treated as a black box — delegate to a dedicated Kustomize linter).
- No `ApplicationSet` support (dynamic generators).
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
- uses: gillesl-dev/argocd-source-lint@v0.1.2
  with:
    path: .
```

### GitLab CI

```yaml
include:
  - component: $CI_SERVER_FQDN/<namespace>/argocd-source-lint/lint@v0.1.2
    inputs:
      scope: manifests/
```

### pre-commit

```yaml
repos:
  - repo: https://github.com/gillesl-dev/argocd-source-lint
    rev: v0.1.2
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
