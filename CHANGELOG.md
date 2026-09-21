# Changelog

All notable changes to this project are documented in this file, in
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

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
