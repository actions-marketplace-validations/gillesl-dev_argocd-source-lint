from __future__ import annotations

from pathlib import Path
from typing import Any

from argocd_source_lint.coverage import covered_documents_for_application
from argocd_source_lint.git_context import external_path_sources
from argocd_source_lint.models import Application, Finding, Severity
from argocd_source_lint.policy import Policy
from argocd_source_lint.rules.base import Rule, external_source_finding

RULE_ID = "unknown-resource-hook"

_HOOK_ANNOTATION = "argocd.argoproj.io/hook"
_HOOK_DELETE_POLICY_ANNOTATION = "argocd.argoproj.io/hook-delete-policy"

# Closed sets confirmed against the official sync-waves docs, not
# assumed. Both annotations accept a comma-separated list of these
# values (same convention as argocd.argoproj.io/sync-options).
_KNOWN_HOOK_VALUES = {"PreSync", "Sync", "Skip", "PostSync", "SyncFail", "PreDelete", "PostDelete"}
_KNOWN_HOOK_DELETE_POLICY_VALUES = {"HookSucceeded", "HookFailed", "BeforeHookCreation"}


class UnknownResourceHookRule(Rule):
    """`argocd.argoproj.io/hook`/`hook-delete-policy` are plain string
    annotations read by the controller at reconcile time -- there's no
    schema enforcing their value against the closed set of recognized
    ones. A misspelled value (`presync`, `HookSuceeded`) most likely
    falls through silently to "not a hook"/"no delete policy", the same
    architecture already confirmed for `syncOptions`
    (`unknown-sync-option`) and `sync-wave`. Slightly lower confidence
    than `unknown-sync-option`: the official docs list the valid values
    but don't spell out the silent-fallthrough behavior for this
    specific pair the way they do for sync options (see DESIGN.md)."""

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
            for source in external_path_sources(app, local_origin):
                findings.append(external_source_finding(RULE_ID, app, source))

            for doc in covered_documents_for_application(app, repo_root, local_origin):
                findings.extend(_check_document(app, doc, severity))

        return findings


def _check_document(app: Application, doc: dict[str, Any], severity: Severity) -> list[Finding]:
    annotations = (doc.get("metadata") or {}).get("annotations")
    if not isinstance(annotations, dict):
        return []

    findings = _check_annotation(
        app, doc, annotations, _HOOK_ANNOTATION, _KNOWN_HOOK_VALUES, severity
    )
    findings += _check_annotation(
        app,
        doc,
        annotations,
        _HOOK_DELETE_POLICY_ANNOTATION,
        _KNOWN_HOOK_DELETE_POLICY_VALUES,
        severity,
    )
    return findings


def _check_annotation(
    app: Application,
    doc: dict[str, Any],
    annotations: dict[str, Any],
    annotation_key: str,
    known_values: set[str],
    severity: Severity,
) -> list[Finding]:
    raw_value = annotations.get(annotation_key)
    if not isinstance(raw_value, str):
        return []

    findings: list[Finding] = []
    for value in (entry.strip() for entry in raw_value.split(",")):
        if value and value not in known_values:
            findings.append(_finding(app, doc, annotation_key, value, severity))
    return findings


def _finding(
    app: Application,
    doc: dict[str, Any],
    annotation_key: str,
    value: str,
    severity: Severity,
) -> Finding:
    kind = doc.get("kind", "?")
    name = (doc.get("metadata") or {}).get("name", "?")
    return Finding(
        rule_id=RULE_ID,
        severity=severity,
        application=app.name,
        message=(
            f"`{annotation_key}: {value}` on `{kind}` `{name}` doesn't match any "
            "ArgoCD-recognized value -- likely a typo; an unrecognized value falls "
            "through silently (the resource is treated as a plain, non-hook "
            "resource) instead of erroring."
        ),
        file=app.source_file,
    )
