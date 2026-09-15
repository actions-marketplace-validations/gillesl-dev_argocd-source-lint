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
- A `path` containing a `kustomization.yaml` or `Chart.yaml` is treated as
  opaque and considered fully covered rather than partially interpreted —
  rendering Kustomize overlays or Helm charts is out of scope for v1
  (delegate to a dedicated Kustomize linter), so guessing at their
  contents would just produce noise on directories the tool can't
  actually interpret.

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
