# Changelog

All notable changes to this project are documented in this file, in
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [0.1.24] - 2026-09-21

### Fixed

- The ApplicationSet `git` generator's own `revision` field
  (`directories`/`files`, independent of any generated Application's
  `targetRevision`) was never read at all — directory/file discovery
  always used the checked-out working tree. A `revision` pinned away
  from HEAD would silently generate Applications from today's directory
  structure instead of the pinned one's, with no finding raised at all
  — worse than the other `unresolvable-generator` cases, which are at
  least flagged. Now resolved against a snapshot of that revision, the
  same mechanism already used for a source's own `targetRevision`
  (`git_context.materialize_revision`, moved there from `coverage.py`
  so both call sites share it). An unresolvable revision is reported
  `unverifiable`, same as `phantom-target`/`broken-values-ref`'s
  shallow-clone case.

## [0.1.23] - 2026-09-21

### Fixed

- SARIF's `$schema` pointed at the spec repo's mutable `master` branch
  instead of GitHub's own recommended
  `https://json.schemastore.org/sarif-2.1.0.json`. Results had no
  `partialFingerprints`, which GitHub's docs call essential for
  matching the same finding across runs — without it, an unrelated
  change elsewhere can make every finding look like a new alert.
- JUnit `<testcase name=...>` was the finding's raw message, and two
  different findings (different file/Application) can share that
  message verbatim — GitLab's JUnit parser silently drops every
  testcase after the first with a duplicate name. A `(#N)` suffix on an
  exact repeat keeps every finding visible.
- README's "pending real PyPI" installation caveat wrongly included the
  pre-commit hook (it builds from this Git repo via `pip install .`,
  never from PyPI, so it already works today) and omitted the GitLab CI
  component (which does `pip install` from the real PyPI index, and is
  genuinely affected).
- README's GitHub Actions example was missing `actions/checkout` —
  without it there's nothing for the action to analyze, and it silently
  "succeeds" with zero findings instead of erroring — and the
  `permissions: security-events: write` (`actions`/`contents: read` on
  private repos) the composite action's `upload-sarif` step needs, which
  GitHub never grants automatically to a composite action.
- README's GitLab CI section overstated the prerequisite: using
  `include: component:` never requires publishing to the CI/CD
  Catalog, only a `README.md` + `templates/` in a project on the same
  GitLab instance, referenced by any ref (tag, branch or commit SHA) —
  confirmed against GitLab's own component docs. Publishing to the
  Catalog is a separate, optional step for public discoverability.

### Added

- Rules now carry `fullDescription`, `helpUri` and
  `defaultConfiguration.level` in the SARIF output (recommended fields
  GitHub's UI uses for filtering/detail pages).

## [0.1.22] - 2026-09-21

### Fixed

- `directory.include`/`exclude` and `.argocd-lint.yaml`'s `exclude_paths`
  now match case-sensitively. `fnmatch.fnmatch` case-folds on Windows,
  which could silently diverge from ArgoCD's own case-sensitive Go
  `filepath.Match` and from a case-sensitive CI runner.

## [0.1.21] - 2026-09-21

### Fixed

- `broken-values-ref` now also checks plain (non-`$ref`) Helm
  `valueFiles` entries against the repo, not just cross-source `$ref`
  entries.

## [0.1.20] - 2026-09-21

### Added

- `malformed-sync-wave` rule: a non-integer
  `argocd.argoproj.io/sync-wave` annotation value, which ArgoCD silently
  falls back to wave 0 for instead of erroring.

## [0.1.19] - 2026-09-21

### Added

- Keycloak Operator and External Secrets Operator signatures to the
  built-in `known_operators` pack.

### Changed

- Clarified the GitLab CI `<namespace>` placeholder (renamed to
  `<your-gitlab-group>`, documented the GitLab CI/CD Catalog publishing
  prerequisite).

## [0.1.18] - 2026-09-21

### Added

- `unknown-resource-hook` rule: an unrecognized
  `argocd.argoproj.io/hook`/`hook-delete-policy` annotation value.
- Zalando Postgres Operator signature to `known_operators`.

### Changed

- `unknown-sync-option` now also checks the per-resource
  `argocd.argoproj.io/sync-options` annotation, not just the
  Application-level `syncOptions`.

## [0.1.17] - 2026-09-21

### Added

- `unknown-sync-option` rule: an Application-level `syncOptions` entry
  that doesn't match any ArgoCD-recognized key.

## [0.1.16] - 2026-09-18

### Added

- `duplicate-application-name` rule: two or more Applications sharing
  the same namespace+name.
- `malformed-ignore-diff-pointer` rule: an `ignoreDifferences`
  `jsonPointers` entry that doesn't start with `/` (RFC 6901).

## [0.1.15] - 2026-09-18

### Added

- `sync-validation-disabled` rule: `Validate=false` in `syncOptions`.

### Fixed

- The ApplicationSet `matrix` generator is now capped at 2 child
  generators, matching ArgoCD's own limit — previously computed a bogus
  N-way cartesian product beyond that.

## [0.1.14] - 2026-09-18

### Added

- `hpa-selfheal-conflict` rule: a `HorizontalPodAutoscaler` and
  `selfHeal: true` both managing `spec.replicas` without
  `ignoreDifferences` and the `RespectIgnoreDifferences` sync option.

## [0.1.13] - 2026-09-18

### Added

- Stale baseline entry detection: a `--write-baseline` entry no longer
  matching any current finding is reported as a count, without
  affecting the exit code.
- JUnit XML reporter (`--format junit`).

## [0.1.12] - 2026-09-18

### Added

- Elastic ECK, RabbitMQ Cluster Operator and Strimzi signatures to the
  built-in `known_operators` pack.

## [0.1.11] - 2026-09-18

### Added

- `project-scope-violation` rule: an Application's source/destination
  outside its AppProject's `sourceRepos`/`destinations` scope.

## [0.1.10] - 2026-09-18

### Added

- `revision-mismatch` rule (info): a source's `targetRevision` differs
  from the checked-out revision.

### Fixed

- `orphan-source`, `missing-ignore-diff` and `double-coverage` now
  resolve a source against its own `targetRevision` when it drifts from
  HEAD, instead of always reading the checked-out working tree — a
  manifest only live at a pinned revision was previously never actually
  read.

## [0.1.9] - 2026-09-18

### Added

- Support for the ApplicationSet `merge` generator (previously always
  flagged `unresolvable-generator`).

## [0.1.8] - 2026-09-15

### Fixed

- An ApplicationSet generator's own `selector` (label filter) is now
  flagged `unresolvable-generator` instead of silently ignored.

## [0.1.7] - 2026-09-15

### Added

- `double-coverage` rule: a file covered by more than one different
  Application's sources at once.

## [0.1.6] - 2026-09-15

Initial public release, published under the `gillesl-dev` GitHub/PyPI
namespace.

### Added

- Core rules: `orphan-source`, `broken-values-ref`,
  `missing-ignore-diff`, `phantom-target`, `unresolvable-generator`.

### Fixed

- The table reporter now shows a placeholder instead of a blank cell
  for `orphan-source` findings, which have no owning Application.
