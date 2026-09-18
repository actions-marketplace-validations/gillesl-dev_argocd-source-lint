from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from argocd_source_lint.coverage import covered_documents_for_application
from argocd_source_lint.git_context import external_path_sources
from argocd_source_lint.models import Application, Finding, KnownOperatorSignature, Severity
from argocd_source_lint.policy import Policy
from argocd_source_lint.rules.base import Rule, external_source_finding

RULE_ID = "missing-ignore-diff"
_BUILT_IN_SIGNATURES_PATH = Path(__file__).parent / "known-operators.yaml"


class MissingIgnoreDiffRule(Rule):
    rule_id = RULE_ID

    def check(
        self,
        applications: list[Application],
        repo_root: Path,
        policy: Policy,
        local_origin: str | None,
    ) -> list[Finding]:
        severity = policy.rules.get(RULE_ID, Severity.WARNING)
        signatures = _load_signatures(policy)
        findings: list[Finding] = []

        for app in applications:
            # Heuristic rule by nature: only Applications with
            # selfHeal active are concerned — without it, ArgoCD never
            # overwrites out-of-Git-managed fields anyway, so the rule has
            # nothing to say about ANY of its sources (including external
            # ones: no point flagging them "out of scope" for a risk that
            # can't occur).
            if not app.sync_policy_self_heal:
                continue

            for source in external_path_sources(app, local_origin):
                findings.append(external_source_finding(RULE_ID, app, source))

            for doc in covered_documents_for_application(app, repo_root, local_origin):
                findings.extend(_check_document(app, doc, signatures, severity))

        return findings


def _check_document(
    app: Application,
    doc: dict[str, Any],
    signatures: list[KnownOperatorSignature],
    severity: Severity,
) -> list[Finding]:
    group_kind = _group_kind(doc)
    if group_kind is None:
        return []
    resource_namespace = (doc.get("metadata") or {}).get("namespace")

    findings: list[Finding] = []
    for signature in signatures:
        if signature.crd_trigger != group_kind:
            continue
        resolved_name = _resolve_path(doc, signature.name_from)
        if not resolved_name:
            continue
        for expected in signature.expect_ignore_on:
            resource_name = expected.name_pattern.format(name=resolved_name)
            if _has_matching_ignore_diff(app, expected.kind, resource_name, resource_namespace):
                continue
            findings.append(
                Finding(
                    rule_id=RULE_ID,
                    severity=severity,
                    application=app.name,
                    message=(
                        f"selfHeal active and `{signature.crd_trigger}` `{resolved_name}` "
                        f"detected, but no `ignoreDifferences` covers "
                        f"`{expected.kind}` `{resource_name}` — ArgoCD risks resetting "
                        "this out-of-Git-managed field on every sync."
                    ),
                    file=app.source_file,
                    line=app.self_heal_line,
                )
            )
    return findings


def _group_kind(doc: dict[str, Any]) -> str | None:
    api_version = str(doc.get("apiVersion", ""))
    kind = doc.get("kind")
    if "/" not in api_version or not kind:
        return None
    group = api_version.split("/", 1)[0]
    return f"{group}/{kind}"


def _resolve_path(doc: dict[str, Any], dotted_path: str) -> str | None:
    value: Any = doc
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value if isinstance(value, str) else None


def _has_matching_ignore_diff(
    app: Application, kind: str, name: str, namespace: str | None
) -> bool:
    """The known derived resources (`known-operators.yaml`) are all core
    kinds (empty `group`) — an `ignoreDifferences` rule explicitly targeting
    another group can therefore never cover them. A rule with no
    `namespace` covers every namespace (just like a missing `name` covers
    every instance); a rule with a `namespace` set must match the
    triggering resource's namespace."""
    for rule in app.ignore_differences:
        if rule.kind not in (kind, "*"):
            continue
        if rule.group not in (None, ""):
            continue
        if rule.namespace is not None and rule.namespace != namespace:
            continue
        if rule.name is None or rule.name == name:
            return True
    return False


def _load_signatures(policy: Policy) -> list[KnownOperatorSignature]:
    yaml = YAML(typ="safe")
    with _BUILT_IN_SIGNATURES_PATH.open("r", encoding="utf-8") as f:
        raw_entries = yaml.load(f) or []
    signatures = [KnownOperatorSignature.model_validate(entry) for entry in raw_entries]
    signatures.extend(policy.known_operators)
    return signatures
