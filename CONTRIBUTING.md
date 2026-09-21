# Contributing to argocd-source-lint

See [DESIGN.md](./DESIGN.md) for the reasoning behind the mono-repo v1
scope and other non-obvious decisions referenced in code comments.

## Setup

```bash
uv sync --extra dev
uv run pytest
```

No cluster access or credentials required: all tests run against real
mini Git repos created on the fly (`tests/conftest.py`), no filesystem
mocks.

CI (`.github/workflows/test.yml`) runs the full suite on every push and
pull request, across Python 3.11-3.13 on both Linux and Windows — keep it
green before requesting a review.

## Project structure

```
src/argocd_source_lint/
├── cli.py               # typer entrypoint
├── models.py             # Application, Source, Finding, Severity...
├── loader.py              # discovery + parsing of Application manifests
├── git_context.py         # local repo detection, mono-repo classification, git primitives
├── fsutil.py               # YAML walk, multi-document parsing
├── coverage.py              # coverage resolution for a `path` source (directory.recurse/include/exclude)
├── policy.py                # loading/merging .argocd-lint.yaml
├── rules/                   # one rule = one Rule class
└── reporters/                # table, json, sarif, gitlab-codequality
```

## Adding a rule

1. Create `rules/my_rule.py`, a class inheriting from `rules.base.Rule`
   with a `rule_id` and a `check(applications, repo_root, policy,
   local_origin) -> list[Finding]` method.
2. Reuse `git_context.local_path_sources`/`external_path_sources` to
   respect the mono-repo v1 scope: check each local source normally, and
   flag each external source as `info`
   (`rules.base.external_source_finding`) rather than silently ignoring
   it — an Application can have both at once (mixed `spec.sources`), so
   never skip the whole Application just because one source is external.
3. Register the rule in `RULES` (`cli.py`).
4. Add a `tests/fixtures/good_repo` fixture (compliant case, already
   shared across rules) and `tests/fixtures/bad_my_rule/` (broken case),
   plus unit tests for edge cases.
5. Dogfood against a real GitOps repo if possible before opening the PR —
   this is what revealed most of the unanticipated coverage gaps during
   initial development (`directory.include`/`exclude`,
   `$ref`/`helm.valueFiles`...).

## Adding an operator to `missing-ignore-diff`

The signature pack (`rules/known-operators.yaml`) is data-driven: no need
to touch Python code to add an operator.

```yaml
- crd_trigger: <group>/<Kind>
  name_from: metadata.name        # dotted path to the name to extract
  expect_ignore_on:
    - kind: Secret
      name_pattern: "{name}-suffix"
```

For an operator that derives one resource *per entry* of a mapping on
the CRD (e.g. one Secret per user) rather than a single resource per
instance, add `name_from_each` (a dotted path to that mapping) — each
key becomes `{user}` alongside `{name}` in `name_pattern`, see the
Zalando Postgres Operator entry in `known-operators.yaml` for a worked
example. Don't add it speculatively: only when the operator's own docs
confirm the derived name for real, never guessed at (see DESIGN.md).

## Code style

- No comments except to explain a non-obvious WHY (a hidden constraint,
  real ArgoCD behavior verified against the docs, a workaround).
- No abstraction before a second real use case (see `coverage.py`,
  `fsutil.py`, the git primitives in `git_context.py`: all extracted
  after being duplicated a second time, not before).
- Every rule must stay usable without cluster access.
- Linted and formatted with [ruff](https://docs.astral.sh/ruff/)
  (config in `pyproject.toml`), enforced in CI:

  ```bash
  uv run ruff check .
  uv run ruff format .
  ```

## Tests

```bash
uv run pytest -v
```

One fixture per rule in a "compliant" version (`good_repo`, shared) and a
"broken" one (`bad_<rule>/`), plus inline tests (`git_repo` fixture) for
edge cases that don't justify a dedicated directory.
