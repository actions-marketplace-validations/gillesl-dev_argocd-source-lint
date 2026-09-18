# Design notes

Background on the non-obvious decisions the code and its comments refer
back to. If you're reading a comment that says "see DESIGN.md", this is
where it's explained.

## Mono-repo v1 scope

The tool only verifies `Application` sources whose `repoURL` matches the
repo it's running in (detected via `git remote get-url origin`). This is
what makes it a pure filesystem/git walker with no network access, no
credentials, and no caching layer: it can run in any CI job that already
has a checkout, with no extra permissions.

Sources pointing at a different repo are never silently skipped — they're
detected and reported as `info` ("out of scope v1 — manual verification
required"), never checked and never ignored without a trace. An
Application can mix local and external sources in the same
`spec.sources` list; each source is classified independently
(`git_context.local_path_sources`/`external_path_sources`), so a genuinely
local source is still fully checked even when a sibling source in the
same Application is external.

Verifying external-repo sources for real (cloning them, caching by
`repoURL` + `targetRevision`) is a natural v2, not a hidden limitation.

## `directory.recurse`/`include`/`exclude` semantics

`orphan-source` and `missing-ignore-diff` both need to know exactly which
files a `path` source covers. The behavior implemented in `coverage.py`
matches real ArgoCD behavior, confirmed against the official docs rather
than assumed:

- `directory.recurse` defaults to `false` — only the files at the root of
  `path` are covered, not subdirectories, unless `recurse: true` is set
  explicitly.
- `directory.include`/`exclude` is a glob pattern, or several comma
  separated ones wrapped in braces (`{a,b}`), matched against the path
  relative to the source's `path`.
- A `path` containing a `Chart.yaml` is treated as opaque and considered
  fully covered rather than partially interpreted — rendering a Helm
  chart's templates is out of scope for v1 (delegate to `helm template`/a
  dedicated linter), so guessing at their contents would just produce
  noise on a directory the tool can't actually interpret.
- A `path` containing a `kustomization.yaml` (or `.yml`/no extension) is
  **not** opaque: `coverage.py` parses it (`resources`/`bases`/
  `components`/`crds`, recursing into a directory reference;
  `patches`/`patchesStrategicMerge`/`patchesJson6902`;
  `configMapGenerator`/`secretGenerator` `files`/`envs`/`envFile`) and
  marks only what's actually referenced as covered — a manifest sitting
  in the overlay but never listed is a real `orphan-source` finding, the
  same signal as an unreferenced file in a plain directory source, one
  level deeper. A reference that doesn't resolve to a local file/directory
  (a git URL, an SCM shorthand) is silently skipped rather than guessed
  at or flagged: verifying a remote resource is out of scope, same
  principle as an external `Application` source.

## SARIF vs GitLab Code Quality

These are two distinct schemas, not two names for the same thing. SARIF
(`reporters/sarif.py`) is what GitHub code scanning consumes; GitLab's
"Code Quality" MR widget (`reporters/gitlab_codequality.py`) consumes a
CodeClimate-derived format instead (`severity: info|minor|major|critical`,
`fingerprint`, `location.lines.begin`) — hence two separate reporters
rather than one shared SARIF-based implementation.

## The `unverifiable` severity

A shallow, single-branch CI checkout (common in CI jobs) may not have a
`targetRevision` fetched locally. `phantom-target` and `broken-values-ref`
both need to distinguish "this path genuinely doesn't exist" from "I
can't tell, the revision isn't fetched" — conflating the two would either
produce false errors on legitimate branches, or silently stop verifying
anything on an incomplete checkout without anyone noticing.

`unverifiable` blocks CI by default (`unverifiable_blocks_ci: true`)
precisely because the silent-failure mode is worse than a noisy one: a
misconfigured shallow clone should be loud, not a quiet blind spot that
looks identical to "everything's fine."

## The baseline file

Adopting the tool on an existing, large mono-repo almost always surfaces
pre-existing issues (decommissioned components never archived, manifests
applied out-of-band and never brought under GitOps) that are legitimate
findings but not something a team can fix before the next commit. Without
a way to accept them, day one of adoption is "CI is red and stays red
until someone clears a backlog" — which either blocks adoption outright or
gets the tool disabled at the first friction.

`.argocd-lint-baseline.yaml` (`baseline.py`) is a flat, plain-YAML list of
accepted findings (`rule_id`, `file`, `application`, `message` — no
opaque hash, so a reviewer can read a PR diff to it and understand exactly
what's being accepted and why). `--write-baseline` snapshots every current
finding into it in one shot; from then on, only *new* findings (not an
exact match in the baseline) are reported and affect the exit code — a
suppressed count is still printed to stderr so the baseline never silently
hides that it's doing something.

The match is exact on all four fields, deliberately no fuzzy/partial
matching: a change to the finding's message (e.g. the path shifting after
a rename) makes it "new" again rather than silently staying suppressed
forever under a stale description. This mirrors the fingerprint already
used by `reporters/gitlab_codequality.py`, kept as two independent
implementations rather than shared — one feeds an opaque MD5 for GitLab's
UI, the other needs the fields spelled out for human review, so
unifying them would only add an indirection neither side needs.

## `Finding.line`

Populating it requires knowing where in the YAML a given field actually
sits, which `ruamel.yaml`'s "safe" loader throws away — so `fsutil.py`
parses in round-trip mode (`typ="rt"`) instead. The returned
`CommentedMap`/`CommentedSeq` still behave as plain `dict`/`list` for
every existing `.get()`/iteration call site; only `loader.py` reaches for
their `.lc` (line/column) attribute to fill `Source.line`,
`Source.helm_value_files_lines` and `Application.self_heal_line`.

The granularity is deliberately "point at the right block", not "point
at the exact character": a finding about a source points at that
source's mapping (where `repoURL:` sits), a `broken-values-ref` finding
points at the specific `valueFiles` entry, `missing-ignore-diff` points
at the `selfHeal: true` key (the field that enables the risk, since
there's no existing `ignoreDifferences` entry to point at — it's about
an absence). `orphan-source`'s main finding is the one deliberate
exception: it stays `None`, because the whole file is the problem, not
one line of it — SARIF correctly renders that as "no region" rather than
a misleading line 1.

## ApplicationSet generators

`applicationset.py` expands each `ApplicationSet` into the `Application`s
its generators would produce, then feeds them into `loader.build_application`
— from that point on a generated `Application` is indistinguishable from
a plain one, so every existing rule applies to it with zero special-casing.
That reuse is the whole point: it's what lets `phantom-target` (or any
other rule) catch a real bug in a generated Application for free.

Supported, because they're resolvable from a local Git checkout alone
(no live cluster/API call, consistent with the tool's core constraint):

- `list` — elements are already inline in the YAML.
- `git.directories`/`git.files` — read the **local working tree**
  directly, not `git show <revision>`. Correct whenever `revision`
  matches what's checked out (`HEAD`, the overwhelming majority of
  real-world usage); a deliberate v1 simplification, not a silent
  approximation, kept for simplicity over the marginal case of a generator
  pinned to some other revision.
- `matrix` — the cartesian product of its child generators' params
  (later keys override earlier ones on collision), as long as every
  child is itself resolvable.
- `merge` — the base (first child) generator's entries, kept even
  without a match in a later generator; a later generator only
  overrides fields on an entry whose `mergeKeys` already match one from
  the base, and its own non-matching entries are discarded, per the
  upstream semantics (confirmed against the official docs, not
  assumed). An unresolvable *base* means no keys to match against at
  all, so the whole `merge` produces nothing (same reasoning as
  `matrix`'s empty cross product); an unresolvable *later* generator
  just contributes no override — the base entries are fully known
  regardless, so they aren't hidden behind the one finding that already
  flags the gap. A `merge` with no `mergeKeys` is flagged
  `unresolvable-generator` outright: the upstream docs don't specify
  matching behavior without one, so this tool doesn't guess at it.

Not supported, each producing one `unresolvable-generator` finding
(`info` by default) instead of guessing: `clusters`, `scmProvider`,
`pullRequest`, `plugin` (all require a live API/cluster call — the tool
has none), and `goTemplate: true` (a different templating engine, Go
templates, not the classic `{{key}}` substitution implemented here). A
`git` generator whose `repoURL` doesn't match the repo being analyzed
is equally out of scope, same principle as an external `Application`
source.

A generator's own `selector` (a label filter on its generated params,
sibling of `list`/`git`/`matrix` in the same generator entry — including
each child generator nested inside a `matrix`) is equally flagged
`unresolvable-generator` rather than expanded as if it weren't there:
evaluating a label match against the generated params without guessing
would need the exact same semantics ArgoCD itself applies, which this
tool doesn't reimplement. Silently ignoring it would risk generating
Applications ArgoCD would actually filter out — the same
never-silently-skip principle as every other out-of-scope generator
here.

`Finding.line` is always `None` for a generated Application: the
template is consumed once per generator output with different params,
so no single YAML line is "the" location of a specific generated app —
the best a reader can do is look at the ApplicationSet's own `template:`
block, which `Finding.file` already points at.

## `double-coverage`

The mirror image of `orphan-source`: instead of "no Application covers
this file", it's "more than one Application covers this file at once".
Both rules (plus `missing-ignore-diff`) share the same per-Application
coverage computation (`coverage.covered_files_for_application`) — they
just group the result differently: `orphan-source` merges every
Application's coverage into one set and flags what's outside it,
`double-coverage` keeps the coverage per-Application and flags a file
whose owner set has more than one entry.

Deliberately scoped to *different* Applications: two sources of the
*same* Application both reaching the same file is one sync loop, not two
fighting each other, so it isn't flagged — the risk this rule targets
(ArgoCD applying the same manifest from two independent reconciliation
loops, flapping between whichever ran last) simply doesn't exist in that
case.

## `targetRevision` drift

`orphan-source`, `missing-ignore-diff` and `double-coverage` all need to
read a local source's actual files — and until this was addressed, they
always read them off the working tree, never off `source.targetRevision`
itself. That's invisible on the overwhelmingly common case (an
Application's `targetRevision` is the branch actually checked out), but
wrong whenever it isn't — e.g. a stable production Application
deliberately pinned to an old tag while an unrelated refactor moves on
past it on `main`. A manifest that still exists (and is still a real
risk) at that tag, but has since been moved/deleted on `main`, would
never be read at all: not a false alarm, a missed one — exactly the
category of silent failure this tool exists to catch, happening inside
the tool itself.

The fix (`coverage._resolved_source_root`): for each local source,
`git_context.revision_matches_checkout` compares `targetRevision` against
what's actually checked out. When it differs, `coverage._materialized_repo_root`
extracts a full snapshot of the repo *as it existed at that revision*
(`git archive <revision>`, piped straight into a throwaway directory via
Python's `tarfile` — no shell `tar` dependency) and every existing
filesystem-based helper (`covered_files_for_source`,
`covered_files_for_kustomize_dir`, opaque-chart detection, ...) runs
against that snapshot completely unchanged, instead of a parallel
git-object-reading implementation that would have to be kept in sync
with it by hand. The snapshot is a full extraction, not just the
source's own `path`, deliberately: a Kustomize `resources:` entry
reaching outside that `path` (a shared base one level up, say) must
still resolve, exactly as it would against the real working tree.
Extracted once per distinct revision and reused across every source
pinned to it within the run; cleaned up at process exit.

Two different things came out of one underlying computation, because two
different rules need two different things from it:

- `covered_files_for_application` — the repo-relative *identity* of each
  covered file (a plain `Path`, not tied to which root — real or
  snapshot — it was actually found under). `orphan-source` and
  `double-coverage` only ever compare/report identities, never read file
  content, so this is all they need.
- `covered_documents_for_application` — the parsed YAML *content* of
  each covered file, read from wherever it actually lives (the snapshot
  for a divergent source). `missing-ignore-diff` is the one rule that
  inspects file content (looking for an at-risk CRD kind), so it uses
  this instead — reading the "as-if-repo_root" identity above would try
  to open a file that may not even exist there anymore.

A revision that isn't resolvable at all (a shallow clone missing the
branch) is left entirely to `phantom-target`/`broken-values-ref`'s
existing `unverifiable` handling (`is_revision_resolvable`) rather than
guessed at here — `revision_matches_checkout` returns `None` for that
case specifically so callers can tell "differs" apart from "unknown."

`rules/revision_mismatch.py` reports the divergence itself, once per
affected source, purely as an FYI (`info` by default, configurable) —
not a correctness caveat, since the rules above already resolved it
correctly: it's there so a human reading the report notices that an
Application is pinned away from HEAD at all, which is easy to miss
otherwise.

## Extension points

- `loader.ApplicationDiscovery` is an interface, not tied to raw YAML —
  `RawManifestDiscovery` is the only implementation in v1, but a
  `HelmRenderedDiscovery` (for Applications generated by a Helm chart
  rather than declared as plain YAML) could implement the same interface
  without touching the rules or reporters.
- `rules/known-operators.yaml` is a data-driven pack for
  `missing-ignore-diff`: adding an operator signature is a YAML change,
  never a code change (see `CONTRIBUTING.md`).
- A Flux adapter (`Kustomization`/`HelmRelease`, with its own broken-ref
  pattern via `valuesFrom`/`postBuild.substituteFrom`) is a natural
  candidate once the ArgoCD-specific v1 has stabilized.
