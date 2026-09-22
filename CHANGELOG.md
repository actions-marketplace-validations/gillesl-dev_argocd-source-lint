# Changelog

All notable changes to this project are documented in this file, in
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [1.0.1] - 2026-09-22

### Fixed

- `action.yml`'s `description` was 140 characters, over GitHub
  Marketplace's 125-character limit — discovered while actually going
  through the "Publish this Action to the GitHub Marketplace" flow,
  which refused to proceed until it was shortened. No change to the
  Python package itself (not republished to PyPI for this reason); the
  git tag/release exists purely so the Marketplace listing can pick up
  the corrected `action.yml` (the `v1.0.0` tag is left as-is, pointing
  at the commit it was actually published from).

## [1.0.0] - 2026-09-22

### Changed

- Version bumped to `1.0.0`, marking the public v1 launch (real PyPI +
  GitHub Marketplace). No functional change from `0.1.36` — every rule,
  reporter, and the two security-audit rounds behind it are unchanged;
  this is the version/metadata declaration that milestone was gated on.
  PyPI classifier updated from `Development Status :: 3 - Alpha` to
  `5 - Production/Stable`.

## [0.1.36] - 2026-09-22

### Security

A second, more thorough audit pass (explicitly requested: "tu en vois
d'autres ? ... je veux en être sûr"), checked systematically by
category rather than opportunistically. Three more real, confirmed
issues:

- `materialize_revision` crashed the whole CLI on a hostile tar
  stream instead of returning `None`. `filter="data"` (PEP 706)
  correctly rejects a `../`-style tar entry — confirmed for real, it
  raises `OutsideDestinationError` rather than extracting outside the
  target directory — but that rejection is itself an exception, and
  nothing caught it. Now wrapped in `try: ... except tarfile.TarError`,
  same effect as the existing "subprocess failed" branch beside it.
- The table reporter interpreted repo-controlled content (an
  Application's own name, a filename, a rule's message) as `rich`
  markup. Confirmed for real: a crafted `metadata.name` containing
  `[link=...]` rendered as an actual clickable hyperlink, and a
  `[bold red on white]`-style tag actually re-styled the row — a
  crafted repo could restyle or spoof this tool's own terminal output.
  Every field except the severity cell (built from this tool's own
  closed enum, never repo content) is now escaped with
  `rich.markup.escape()`.
- The ApplicationSet `matrix` generator's cartesian product had no
  size cap — only the "max 2 children" structural cap existed, nothing
  about how large those two children's own param lists could be.
  Confirmed for real: two `list` generators of 5,000 small elements
  each (individually well under the alias-bomb node budget, since that
  budget catches a densely aliased document, not a large flat one)
  produced 25,000,000 combinations in ~7s for the combine step alone,
  before a single generated Application is even built. Capped at
  10,000 combinations, checked before the cartesian product is built.

Checked and confirmed not vulnerable: `ruamel.yaml`'s loaders don't
execute Python object construction from YAML tags; the JUnit/SARIF/
JSON/GitLab reporters all escape properly (`ElementTree`/`json.dumps`,
never manual string concatenation); `pip-audit` found nothing against
the exact resolved dependency versions.

Documented as a limitation, not a code fix: `.argocd-lint.yaml` and
`.argocd-lint-baseline.yaml` are repo content themselves, so an
untrusted fork's PR can edit either in the same PR that introduces
what it would otherwise flag — protect both with `CODEOWNERS`/branch
protection if running against untrusted forks.

## [0.1.35] - 2026-09-22

### Security

- `globs.py`'s `match_glob` (shared by the ApplicationSet `git`
  generator's `directories`/`files` `path:` and
  `project-scope-violation`'s `sourceRepos`/`destinations`) translated
  a glob pattern into a backtracking regex. Confirmed for real: a
  pattern shaped like `*a*a*a...*a!` (~40 repetitions) against a
  non-matching candidate of `a`s hung indefinitely — a classic ReDoS,
  and both the pattern and the candidate are repo-controlled here.
  `match_glob` now tokenizes the pattern once and runs a
  dynamic-programming scan over the candidate instead —
  `O(len(pattern) x len(candidate))` by construction, regardless of how
  many wildcards the pattern has, rather than relying on an input-size
  limit that would still be exponential below the limit.

## [0.1.34] - 2026-09-22

### Security

- A source's own `path` (e.g. `path: ../outside-secret`) was joined
  onto the repo root with no check that the result stayed inside it.
  Confirmed for real: this crashed `covered_files_for_application`
  (`orphan-source`, `double-coverage`) and made
  `covered_documents_for_application` (`missing-ignore-diff`,
  `hpa-selfheal-conflict`, `unknown-sync-option`,
  `unknown-resource-hook`, `malformed-sync-wave`) silently read and
  surface a file's full content from anywhere reachable via `../` from
  the repo root — a straight local file disclosure, not just a crash.
- A second, independent instance of the same bug: a Kustomize overlay's
  own `resources`/`bases`/`components`/`crds`/`patches*`/generator
  entries were resolved the same unguarded way. This one comes from
  *tracked YAML content*, not ArgoCD's own schema, so it doesn't even
  need a crafted `Application` — any commit touching a
  `kustomization.yaml` can reach it, and the recursion means a nested
  overlay chain could walk arbitrarily far outside the repo.
- Both fixed by threading the repo/snapshot root through the whole
  resolution chain and checking every resolved path against it
  (`Path.is_relative_to`) before it's ever stat'd, walked, or read —
  never filtered out of the result afterward, which would still touch
  arbitrary filesystem locations along the way.

## [0.1.33] - 2026-09-22

### Security

- A `targetRevision` (or an ApplicationSet `git` generator's own
  `revision`) is repo-controlled YAML, but was passed straight through
  as a positional argument to `git`. A value like
  `--remote=https://<host>/x` is read by `git` as a *flag*, not a
  revision — confirmed for real: `git archive` with that value spends
  the full TCP connect timeout actually reaching out to `<host>`
  instead of failing to parse, a live SSRF primitive from inside
  whatever CI job runs this tool, breaking the "no network access, no
  credentials" guarantee the tool is built on. Every function in
  `git_context.py` that shells out with a `revision`
  (`is_revision_resolvable`, `_resolve_commit`, `materialize_revision`,
  `list_tree_paths`) now rejects a `-`-prefixed value before it ever
  reaches a `git` subprocess — a real revision never starts with `-`
  in the first place, so no legitimate value is affected. A rejected
  revision is treated exactly like any other unresolvable one, same
  `unverifiable` handling already in place.

## [0.1.32] - 2026-09-22

### Added

- `malformed-ignore-diff-jq-expression` rule: an `ignoreDifferences`
  `jqPathExpressions` entry that doesn't start with `.` — every real
  example in ArgoCD's own docs does, the same convention `jsonPointers`
  has for `/`. Usually a `jsonPointers`-style path pasted into the
  wrong sibling field. Confirmed against ArgoCD's own source
  (`NewIgnoreNormalizer`): a parse failure here voids the *entire*
  `ignoreDifferences` list for that Application, not just this entry —
  a wider blast radius than a bad `jsonPointers` entry, and matching
  real reports of `jqPathExpressions` that "apply without errors but
  don't actually do anything." Deliberately as narrow as
  `malformed-ignore-diff-pointer`: no `jq` engine involved, no attempt
  to catch ArgoCD's own version-dependent evaluation quirks.

### Fixed

- `policy.DEFAULT_RULE_SEVERITIES` and `reporters/sarif.py`'s
  `_RULES_METADATA` are two more manually maintained rule-ID lists,
  same shape as the `cli.RULES` gap closed in `0.1.31` — a rule
  missing from either wouldn't crash, just silently lose its
  configurable severity or its SARIF `fullDescription`/`helpUri`. Two
  new tests assert both stay in sync with the real rule set.

## [0.1.31] - 2026-09-22

### Fixed

- Five rules (`missing-ignore-diff`, `hpa-selfheal-conflict`,
  `unknown-sync-option`, `unknown-resource-hook`, `malformed-sync-wave`)
  and two more (`orphan-source`, `double-coverage`) each independently
  re-walked and re-parsed the same Application's covered source
  directory — confirmed for real: 40 Applications x 15 covered files
  each, across just 3 of those rules, cost ~4.9s of pure re-walking and
  re-parsing. `fsutil.load_yaml_documents` now caches by resolved file
  path and `coverage.covered_files_for_source` caches by
  `(source_dir, directory_recurse, directory_include,
  directory_exclude)` — both reset via `clear_caches`, same story as
  every other cache here.
- `phantom-target` ran one `git ls-tree` subprocess per Application to
  check its `path` exists at `targetRevision`, even though most
  Applications in a real repo share the same revision — confirmed for
  real: 40 Applications with distinct paths cost ~2.3s of subprocess
  spawns. `git_context.tree_paths_at_revision` now lists the whole tree
  once per `(repo_root, revision)`, and `path_has_tracked_files`
  answers the per-path question against that in-memory listing instead.
  `broken-values-ref`'s own equivalent local cache is now backed by the
  same shared one.
- A `Rule` subclass that exists under `rules/` but is never added to
  `cli.RULES` stayed invisible to the whole test suite: its own unit
  test instantiates and calls it directly, so it could pass while the
  real CLI never ran it at all. Confirmed for real with a throwaway
  rule module. `test_every_rule_class_is_registered_in_cli_rules`
  force-imports every module under `rules/` and asserts none are
  missing from `RULES`.

### Changed

- `orphan-source` imported `broken_values_ref.py`'s `_parse_ref_entry`
  across module boundaries despite its underscore signaling "private" —
  it already was shared, just not admitting it. Renamed to
  `parse_ref_entry`, and the `{source.ref: source for source in
  app.sources if source.ref}` comprehension duplicated verbatim in both
  files is now the shared `ref_sources_by_name`. No behavior change.

## [0.1.30] - 2026-09-21

### Changed

- `applicationset.py`'s four generator resolvers
  (`_resolve_generator`/`_resolve_git`/`_resolve_matrix`/
  `_resolve_merge`) each repeated the same five parameters
  (`repo_root`, `local_origin`, `appset_name`, `source_file`,
  `severity`) alongside their own generator dict. Replaced with a
  single `GeneratorContext`. Internal only, no behavior change, no
  call site outside this file.

## [0.1.29] - 2026-09-21

### Fixed

- `RawManifestDiscovery`, the ApplicationSet walker and
  `discover_app_projects` each independently walked the entire repo
  and parsed every YAML file, each looking for a different `kind` —
  three full passes over the same files. Confirmed for real: 2,000
  plain manifests (none of them an Application/ApplicationSet/
  AppProject) cost ~5s total across the three passes.
  `fsutil.discover_documents` now does that walk once and caches it
  (same scoping as `_resolve_commit`'s cache, reset via
  `clear_caches`); the three callers just filter the shared result by
  `kind`. Every existing call site's own signature is unchanged.

## [0.1.28] - 2026-09-21

### Fixed

- 50 Applications sharing `targetRevision: HEAD` cost 702 identical
  `git rev-parse` calls in a single run — confirmed for real, not
  estimated: ~58 seconds on Windows, where subprocess spawn dominates
  the cost. Every local-source rule independently re-resolved the same
  revision against the same checkout with no caching at all.
  `git_context._resolve_commit` now caches by `(repo_root, revision)`
  for the life of one CLI invocation, collapsing the same run to 1
  call and ~5 seconds. A caching change must never alter results, only
  speed — verified: identical findings before and after, and a
  dedicated test confirms a repo mutated between two invocations still
  gets a fresh answer (the one scenario a naive process-lifetime cache
  could get wrong).

## [0.1.27] - 2026-09-21

### Fixed

- A directory symlink/junction pointing back at one of its own
  ancestors made file discovery run forever — confirmed for real with
  a Windows junction (a few KB on disk). Neither `Path.rglob` nor even
  `os.walk(directory, followlinks=False)` protect against it: a
  junction isn't reported as a symlink, so that guard never triggers.
  `fsutil.walk_tree` replaces three independent, unguarded `rglob`
  call sites (`iter_yaml_files`, and the ApplicationSet `git`
  generator's own directory/file discovery) with one shared,
  cycle-safe walk — each directory resolved once and never
  re-descended into, the same identity-tracking already used for a
  Kustomize `resources:` cycle. As a side effect, a file reachable
  through two different non-cyclic paths to the same physical
  directory is now found once per traversal instead of double-counted.

## [0.1.26] - 2026-09-21

### Fixed

- A YAML "billion laughs" alias bomb (a few hundred bytes, nested
  anchors each referencing the previous one twice) hung the tool
  indefinitely — confirmed for real against both an ApplicationSet
  `git` generator's `files:` params file and a manifest with a bombed
  `apiVersion` field. `ruamel.yaml`'s own loader is safe (an alias
  resolves to the same object, not a copy); the hang came from code
  downstream blindly stringifying the result. `fsutil.load_yaml_documents`
  now rejects a document whose fully-expanded size would be
  unreasonable (`is_within_budget`, computed via memoized recursion so
  the check itself stays cheap), the same way it already drops a file
  that fails to parse — closing this at the one place virtually every
  document is read through, rather than patching each of the five
  near-identical unguarded `str()` call sites this audit found.

## [0.1.25] - 2026-09-21

### Fixed

- A missing `git` binary silently degraded every result into false
  `orphan-source`/`double-coverage` positives instead of a clear error:
  `get_origin_url` was the only call site that handled it, by returning
  `None` — the exact same value it returns for "no `origin` remote
  configured," which every rule already (correctly, for that case)
  treats as "nothing here is local." Reproduced against
  `python:3.11-slim`, the base image `templates/lint.yml` itself
  recommends, which doesn't ship `git`. Fixed on both ends: the CLI now
  checks `git` is on PATH at startup and exits with a clear error
  instead of degrading, and `templates/lint.yml` installs `git` in
  `before_script`.

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
