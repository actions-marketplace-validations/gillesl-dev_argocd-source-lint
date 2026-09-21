from __future__ import annotations

from pathlib import Path
from typing import Any

from argocd_source_lint.coverage import covered_documents_for_application
from argocd_source_lint.git_context import external_path_sources
from argocd_source_lint.models import Application, Finding, Severity
from argocd_source_lint.policy import Policy
from argocd_source_lint.rules.base import Rule, external_source_finding

RULE_ID = "unknown-sync-option"

_RESOURCE_SYNC_OPTIONS_ANNOTATION = "argocd.argoproj.io/sync-options"

# The complete, closed set of spec.syncPolicy.syncOptions keys ArgoCD
# recognizes (confirmed against the official sync-options docs, not
# assumed) -- exact PascalCase, matched as a literal "Key=Value" string
# by ArgoCD itself, same mechanism already relied on for
# RespectIgnoreDifferences in hpa-selfheal-conflict. A key outside this
# set is never an error upstream: ArgoCD silently ignores an
# unrecognized sync option rather than rejecting it.
_KNOWN_SYNC_OPTION_KEYS = {
    "Prune",
    "Validate",
    "SkipDryRunOnMissingResource",
    "Delete",
    "ApplyOutOfSyncOnly",
    "PrunePropagationPolicy",
    "PruneLast",
    "Replace",
    "ServerSideApply",
    "ClientSideApplyMigration",
    "FailOnSharedResource",
    "RespectIgnoreDifferences",
    "CreateNamespace",
}

# The smaller, distinct set recognized on the per-resource
# `argocd.argoproj.io/sync-options` annotation (also confirmed against
# the official docs) -- e.g. `Force` only exists here, while
# `ApplyOutOfSyncOnly`/`RespectIgnoreDifferences`/`CreateNamespace`/
# `FailOnSharedResource`/`ClientSideApplyMigration`/`PrunePropagationPolicy`
# are Application-level-only concepts that don't apply to one resource.
_KNOWN_RESOURCE_SYNC_OPTION_KEYS = {
    "Prune",
    "Validate",
    "SkipDryRunOnMissingResource",
    "Delete",
    "PruneLast",
    "Replace",
    "Force",
    "ServerSideApply",
}


class UnknownSyncOptionRule(Rule):
    """A `syncOptions` entry -- at the Application level
    (`spec.syncPolicy.syncOptions`) or per-resource (the
    `argocd.argoproj.io/sync-options` annotation) -- is matched by
    ArgoCD as a literal `Key=Value` string -- there's no schema
    validation on it, so a wrong case (`respectIgnoreDifferences=true`)
    or a misspelled key (`PruneLatest=true`) is never rejected, just
    silently a no-op. The key portion is checked against the closed,
    documented set rather than the value: the exact accepted
    values/casing per key are less consistently documented, so
    validating only the key keeps this an objective check instead of a
    guess (same principle as `malformed-ignore-diff-pointer`)."""

    rule_id = RULE_ID

    def check(
        self,
        applications: list[Application],
        repo_root: Path,
        policy: Policy,
        local_origin: str | None,
    ) -> list[Finding]:
        severity = policy.rules.get(RULE_ID, Severity.WARNING)
        findings: list[Finding] = []

        for app in applications:
            for option in app.sync_options:
                key = option.split("=", 1)[0]
                if key not in _KNOWN_SYNC_OPTION_KEYS:
                    findings.append(_app_level_finding(app, option, severity))

            for source in external_path_sources(app, local_origin):
                findings.append(external_source_finding(RULE_ID, app, source))

            for doc in covered_documents_for_application(app, repo_root, local_origin):
                findings.extend(_check_resource_annotation(app, doc, severity))

        return findings


def _check_resource_annotation(
    app: Application, doc: dict[str, Any], severity: Severity
) -> list[Finding]:
    annotations = (doc.get("metadata") or {}).get("annotations")
    if not isinstance(annotations, dict):
        return []

    raw_value = annotations.get(_RESOURCE_SYNC_OPTIONS_ANNOTATION)
    if not isinstance(raw_value, str):
        return []

    findings: list[Finding] = []
    for option in (entry.strip() for entry in raw_value.split(",")):
        key = option.split("=", 1)[0]
        if option and key not in _KNOWN_RESOURCE_SYNC_OPTION_KEYS:
            findings.append(_resource_level_finding(app, doc, option, severity))
    return findings


def _app_level_finding(app: Application, option: str, severity: Severity) -> Finding:
    return Finding(
        rule_id=RULE_ID,
        severity=severity,
        application=app.name,
        message=(
            f"`{option}` in `syncOptions` doesn't match any of the "
            f"{len(_KNOWN_SYNC_OPTION_KEYS)} ArgoCD-recognized sync option keys "
            "(case-sensitive, e.g. `RespectIgnoreDifferences`, `CreateNamespace`) -- "
            "likely a typo; ArgoCD silently ignores an unrecognized sync option "
            "instead of erroring, so this has no effect at all."
        ),
        file=app.source_file,
        line=app.sync_options_line,
    )


def _resource_level_finding(
    app: Application, doc: dict[str, Any], option: str, severity: Severity
) -> Finding:
    kind = doc.get("kind", "?")
    name = (doc.get("metadata") or {}).get("name", "?")
    return Finding(
        rule_id=RULE_ID,
        severity=severity,
        application=app.name,
        message=(
            f"`{option}` in the `{_RESOURCE_SYNC_OPTIONS_ANNOTATION}` annotation on "
            f"`{kind}` `{name}` doesn't match any of the "
            f"{len(_KNOWN_RESOURCE_SYNC_OPTION_KEYS)} ArgoCD-recognized per-resource "
            "sync option keys (case-sensitive, e.g. `Force`, `ServerSideApply`) -- "
            "likely a typo; ArgoCD silently ignores an unrecognized sync option "
            "instead of erroring, so this has no effect at all."
        ),
        file=app.source_file,
    )
