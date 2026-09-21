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

## The JUnit reporter's severity mapping

JUnit XML (`reporters/junit.py`) has no native "warning"/"info" level —
only a passing testcase, `<failure>`, `<error>`, or `<skipped>`. One
`<testcase>` per finding, mapped to match this tool's own exit-code
semantics rather than inventing a separate scale: `error` and
`unverifiable` (the two severities that actually block CI by default,
see `cli._exit_code`) become `<failure>`; `warning`/`info` become
`<skipped>` rather than a silent pass — they're still something to look
at, and a skipped testcase renders visually distinct (grey, not green)
in Jenkins/GitLab/Azure DevOps alike. Deliberately not policy-aware
(doesn't consult `unverifiable_blocks_ci`): every other reporter here
(SARIF, GitLab Code Quality) already maps `unverifiable` to a fixed
level regardless of whether it currently blocks CI, so this follows the
same established precedent instead of being the one exception.

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

The reverse problem exists too: an entry accepted once but never
revisited, for an issue since fixed, renamed, or removed, still sits in
the file forever — a baseline that only ever grows stops being
something a reviewer can actually read. `stale_baseline_entries`
(`baseline.py`) reports a count of exactly this to stderr on every run
(never affecting the exit code — a stale entry is dead weight, not a
new risk), nudging towards re-running `--write-baseline` to drop them.
It's deliberately a nudge, not an enforced check: some teams may want
their baseline to *stay* stable across a temporary dip in findings, and
a hard failure here would fight that.

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
  child is itself resolvable. Capped at exactly 2 child generators,
  matching ArgoCD's own real limit (confirmed against the official
  docs): the upstream controller "reports an error on generation" for a
  3rd, it doesn't just combine unpredictably. More than 2 is flagged
  `unresolvable-generator` instead of computing a cartesian product
  ArgoCD itself would never actually produce — an earlier version of
  this tool had no such cap, which would have silently reported
  Applications that don't exist.
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

## `project-scope-violation`

An Application's `spec.project` restricts which repos it may sync from
and which destinations it may sync to (`AppProject.spec.sourceRepos`/
`destinations`). Outside that scope, ArgoCD refuses to sync — but
nothing in the repo itself looks wrong, so from a Git-only point of view
it's silent, exactly the failure mode this tool exists for. It's also
fully static: pure string/glob matching between manifests already in
the repo (the Application and its own `AppProject`), no cluster access
needed.

The matching semantics are deliberately *not* a single shared helper
applied uniformly — because ArgoCD itself doesn't use one. Read directly
from ArgoCD's own source
(`AppProject.IsSourcePermitted`/`isDestinationMatched` in
`app_project_types.go`) rather than assumed, since guessing here nearly
produced two confidently wrong results during development:

- `sourceRepos`: a bare `*` always matches unconditionally — a special
  case in ArgoCD's own `globMatch` wrapper that bypasses the glob engine
  entirely, not something a general-purpose glob library would do on its
  own. Any other pattern is a `/`-segment-bounded glob (`*` within one
  segment, `**` crosses — the same semantics as the `git` ApplicationSet
  generator's `directories`/`files`, see above), matched against both
  the pattern and the Application's `repoURL` normalized the same way
  `git_context.normalize_repo_url` already does elsewhere in this tool
  (ArgoCD normalizes both sides too, via its own `git.NormalizeGitURL`),
  so a harmless ssh-vs-https or trailing-`.git` difference isn't a false
  violation.
- `destinations` (`server`/`name`/`namespace`): an *unbounded* glob —
  ArgoCD calls the same underlying matcher without any separator
  argument here, so `*` crosses `/` freely, unlike `sourceRepos`.
  Deliberately not `fnmatch.fnmatch` (case-insensitive on Windows) but
  `fnmatchcase`: a namespace/server/cluster name is case-sensitive data,
  not a filesystem path, and matching should be identical however the
  tool is run.
- `destination.name` vs `destination.server`: resolving one against the
  other requires knowing which live cluster a nickname (`name`) actually
  points to — cluster/API access this tool doesn't have. When the
  Application and its `AppProject` destinations don't share a
  comparable field (app uses `server`, every project entry only has
  `name`, or vice versa), that's flagged `info` rather than guessed at
  either way — matching everything or matching nothing would both be a
  coin flip.
- A negated (`!`-prefixed) `sourceRepos`/`destinations` entry is flagged
  `info` instead of evaluated: ArgoCD's own negation logic (a deny match
  short-circuits, but a deny *non*-match counts toward the positive
  total too) is confusing enough that the community has open bug reports
  about its surprises — not something to reimplement with confidence.

A `project:` not found anywhere in the repo is either ArgoCD's own
auto-created, permissive `"default"` (silently assumed, since flagging
it would be noise on the overwhelming majority of repos that never
declare it explicitly) or a named project genuinely managed elsewhere —
flagged `info` in the second case, never silently treated as "no
restriction" the way a missing `"default"` is.

## `hpa-selfheal-conflict`

A `HorizontalPodAutoscaler` and `selfHeal: true` both trying to own the
same `Deployment`/`StatefulSet`'s `spec.replicas` is one of the most
commonly reported ArgoCD footguns: the HPA scales the workload, ArgoCD's
next self-heal reconciliation sees a live value that no longer matches
Git and reverts it, the HPA scales it back — a permanent fight, fully
silent from the Application's health/sync status (both stay green).

The non-obvious part, confirmed against ArgoCD's own
[diffing](https://argo-cd.readthedocs.io/en/stable/user-guide/diffing/)/
[sync-options](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/)
docs rather than assumed: `ignoreDifferences` alone does **not** fix
this. It only affects the *diff* used to compute `OutOfSync` — during an
actual sync, the desired manifest is still applied as-is, replicas
included, unless the `RespectIgnoreDifferences=true` sync option is also
set. A repo with `ignoreDifferences` for the Deployment but missing that
sync option looks correctly configured to a human reviewer and is still
broken — which is exactly why this rule checks for *both*, and reports a
distinct message when only one is present, rather than a single
generic "misconfigured" finding.

The HPA's target is resolved from its own `scaleTargetRef`
(`kind`/`name`, and `apiVersion` when present to derive the Kubernetes
API group for matching against `ignoreDifferences.group`) — never by
searching for a matching Deployment manifest in the repo. This keeps the
rule correct even when the target is rendered by a Helm chart this tool
doesn't template, and avoids a false negative when the target simply
isn't declared as a plain file at all. When `scaleTargetRef.apiVersion`
is absent, the group is looked up in a small built-in map (`Deployment`/
`StatefulSet`/`ReplicaSet` → `apps`, `ReplicationController` → core) —
an unrecognized `kind` outside that map (e.g. a custom scalable CRD like
Argo Rollouts' `Rollout`) is silently skipped rather than guessed at.

## `sync-validation-disabled`

`Validate=false` in `syncOptions` skips the Kubernetes API server's
schema validation on every sync. It's a legitimate escape hatch for a
CRD whose OpenAPI schema is itself broken upstream, but it's also a
common way to make a validation error on a genuinely wrong manifest go
away without fixing the manifest — and, once added, easy to forget
about since nothing about the Application's health/sync status hints
that validation is off. `info` by default (not `warning`/`error`): the
flag is explicit in the manifest, not hidden the way this tool's other
findings are, so it's a nudge to double-check, not a presumed mistake.

## `duplicate-application-name`

ArgoCD keys an `Application` by `(namespace, name)` — its own internal
identity, the same as any other Kubernetes object. Two manifests
declaring the same pair don't show anything wrong when read on their
own; the collision only surfaces once both are applied, and even then
as one silently overwriting or fighting the other rather than a clear
error (confirmed against several real reports, not assumed —
[argoproj/argo-cd#9420](https://github.com/argoproj/argo-cd/issues/9420),
[#23808](https://github.com/argoproj/argo-cd/issues/23808), which notes
an `ApplicationSet`-generated duplicate "replaces previous instance
without warning"). Exactly the class of bug this tool exists for.

The check runs against the `applications` list a rule receives as-is —
by the time rules run, that list already merges plain manifests with
every `ApplicationSet`-generated `Application` (see `cli.py`), so a
collision is caught the same way regardless of which side of the
collision is templated. Two generated entries colliding with each other
(the same `ApplicationSet`'s own generator rendering the same name
twice, e.g. a typo'd `elements` list) share the same `source_file` — the
`ApplicationSet`'s own manifest, per `Finding.line`'s existing note
above — so it's de-duplicated to one mention rather than listed twice.

`namespace` defaults to `"argocd"` when omitted (same as ArgoCD itself,
consistent with `project-scope-violation`'s own default handling) — in
practice almost every real repo puts every Application in the same
namespace, so this mostly reduces to "duplicate name", full stop; the
namespace is tracked mainly for the rare "Applications in any namespace"
setup, not because same-name-different-namespace collisions are known
to be common.

## `malformed-ignore-diff-pointer`

`ignoreDifferences[].jsonPointers` follows
[RFC 6901](https://www.rfc-editor.org/rfc/rfc6901): every pointer must
start with `/`, one segment per `/`. A pointer written as `spec.replicas`
or `spec/replicas` (missing the leading slash) resolves to nothing, so
the rule silently ignores nothing — the field it was meant to protect
still shows up in every diff, and still gets reverted on every
`selfHeal` reconciliation exactly as if `ignoreDifferences` had never
been written. A genuinely common mistake, not a hypothetical one: dot
notation copied from a different tool's path syntax (JSONPath, Lua) is
the most frequent variant reported.

Deliberately not a heuristic: RFC 6901 makes "does this start with `/`"
an objective yes/no, unlike e.g. `missing-ignore-diff`'s pattern
matching. `jqPathExpressions` (the other `ignoreDifferences` matcher)
isn't checked the same way — validating `jq` syntax would need an actual
`jq` parser (a `libjq` binding), a real dependency for uncertain payoff,
and most of the community-reported `jqPathExpressions` problems turn out
to be ArgoCD-side behavior quirks that vary by version rather than
authoring mistakes a static check could catch reliably.

## `unknown-sync-option`

`spec.syncPolicy.syncOptions` entries are matched by ArgoCD as literal
`Key=Value` strings — there's no schema validation on the key or the
value, so a wrong case (`respectIgnoreDifferences=true` instead of
`RespectIgnoreDifferences=true`) or a misspelled key
(`PruneLatest=true`) is never rejected. It's just never recognized
either, so the option has zero effect: exactly the same silent-no-op
shape `hpa-selfheal-conflict` already relies on for
`RespectIgnoreDifferences` specifically, generalized to the entire
option set.

The [official sync-options docs](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/)
document a closed, exact list of 13 keys (confirmed there, not assumed):
`Prune`, `Validate`, `SkipDryRunOnMissingResource`, `Delete`,
`ApplyOutOfSyncOnly`, `PrunePropagationPolicy`, `PruneLast`, `Replace`,
`ServerSideApply`, `ClientSideApplyMigration`, `FailOnSharedResource`,
`RespectIgnoreDifferences`, `CreateNamespace` — all PascalCase. Only the
**key** portion (before `=`) is checked against that set, deliberately
not the value: the exact accepted values/casing per key (`=true` only?
`=false` too? `=confirm`? `PrunePropagationPolicy`'s three enum values)
aren't consistently documented across every key, so validating values
too would risk a false positive on a legitimate but less-common
combination — the same "don't guess" principle as
`malformed-ignore-diff-pointer` restricting itself to the one
unambiguous RFC 6901 rule (a leading `/`) rather than every possible
way a pointer could be semantically wrong.

The per-resource `argocd.argoproj.io/sync-options` annotation is a
related but genuinely distinct, smaller key set (confirmed against the
same docs) — `Force` only exists here, while `ApplyOutOfSyncOnly`/
`RespectIgnoreDifferences`/`CreateNamespace`/`FailOnSharedResource`/
`ClientSideApplyMigration`/`PrunePropagationPolicy` are
Application-level-only concepts that don't apply to a single resource.
This rule checks both: the Application-level list directly, and the
per-resource annotation by scanning every covered document the same
way `missing-ignore-diff`/`hpa-selfheal-conflict` already do — a key
that's valid at one level but not the other (e.g.
`RespectIgnoreDifferences=true` on a single resource) is still flagged,
since it's just as much a no-op there.

## `unknown-resource-hook`

`argocd.argoproj.io/hook` and `argocd.argoproj.io/hook-delete-policy`
are read by the controller as plain annotation strings — like
`sync-options`/`sync-wave`, there's no schema enforcing their value
against a closed set. A misspelled value (`presync`, `HookSuceeded`)
most likely falls through silently: the resource is just treated as a
normal, non-hook resource, or as a hook with no delete policy at all,
applied and left in place with everything else rather than erroring.

Both annotations accept a comma-separated list, same convention as
`sync-options`. The valid values (confirmed against the official
sync-waves docs, not assumed) are `PreSync`/`Sync`/`Skip`/`PostSync`/
`SyncFail`/`PreDelete`/`PostDelete` for `hook`, and `HookSucceeded`/
`HookFailed`/`BeforeHookCreation` for `hook-delete-policy`.

Slightly lower confidence than `unknown-sync-option`, worth calling out
explicitly rather than glossing over: the sync-options docs state in so
many words that an unrecognized option has no effect, but the
sync-waves docs merely *list* the valid hook values without spelling
out what happens to an invalid one. The silent-fallthrough behavior
here is inferred from the same architecture (annotations are unvalidated
strings, consistently confirmed for every other case checked this way),
not quoted directly — hence `unknown-resource-hook` staying ranked
behind `unknown-sync-option` when this was prioritized.

## Extension points

- `loader.ApplicationDiscovery` is an interface, not tied to raw YAML —
  `RawManifestDiscovery` is the only implementation in v1, but a
  `HelmRenderedDiscovery` (for Applications generated by a Helm chart
  rather than declared as plain YAML) could implement the same interface
  without touching the rules or reporters.
- `rules/known-operators.yaml` is a data-driven pack for
  `missing-ignore-diff`: adding an operator signature is a YAML change,
  never a code change (see `CONTRIBUTING.md`). Most operators derive a
  single resource name from a single scalar field (`metadata.name`,
  `spec.secretName`) — `name_from_each` is the escape hatch for the
  minority that don't: Zalando's `postgresql` CRD generates one Secret
  *per entry* of `spec.users` (`{username}.{clustername}.credentials.postgresql.acid.zalan.do`,
  confirmed against the operator's own docs), so `name_from_each:
  spec.users` iterates that mapping's keys as `{user}`, alongside the
  usual `{name}` from `name_from`. MariaDB Operator's root/user
  passwords were considered too, and dropped: their Secret name is a
  free-form field the user themselves sets on the CR
  (`rootPasswordSecretKeyRef.name`), not something the operator derives
  from `metadata.name` — nothing here to encode as a signature without
  guessing at a name that doesn't actually follow a fixed convention.
- A Flux adapter (`Kustomization`/`HelmRelease`, with its own broken-ref
  pattern via `valuesFrom`/`postBuild.substituteFrom`) is a natural
  candidate once the ArgoCD-specific v1 has stabilized.
