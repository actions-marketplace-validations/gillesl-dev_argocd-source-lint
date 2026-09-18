from __future__ import annotations

import json

from argocd_source_lint import tool_version
from argocd_source_lint.models import Finding, Severity

_INFORMATION_URI = "https://github.com/gillesl-dev/argocd-source-lint"

_RULES_METADATA = {
    "orphan-source": "Manifest present in the repo but not covered by any declared source.",
    "broken-values-ref": "$ref in a Helm valueFiles entry with no matching source or file.",
    "missing-ignore-diff": "Known at-risk kind with no ignoreDifferences while selfHeal is active.",
    "phantom-target": "targetRevision/path resolves to nothing in the repo.",
    "unresolvable-generator": (
        "An ApplicationSet generator requires live cluster/API access, or "
        "Go-template rendering — out of scope v1."
    ),
    "double-coverage": "A file covered by more than one different Application at once.",
    "revision-mismatch": (
        "A source's targetRevision differs from the checked-out revision -- "
        "disk-based rules may not reflect what ArgoCD actually syncs."
    ),
}

_LEVEL_BY_SEVERITY = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INFO: "note",
    Severity.UNVERIFIABLE: "warning",
}


def render_findings(findings: list[Finding]) -> str:
    payload = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "argocd-source-lint",
                        "informationUri": _INFORMATION_URI,
                        "version": tool_version(),
                        "rules": [
                            {
                                "id": rule_id,
                                "shortDescription": {"text": description},
                            }
                            for rule_id, description in _RULES_METADATA.items()
                        ],
                    }
                },
                "results": [_result(finding) for finding in findings],
            }
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _result(finding: Finding) -> dict:
    physical_location: dict = {"artifactLocation": {"uri": finding.file.as_posix()}}
    if finding.line is not None:
        physical_location["region"] = {"startLine": finding.line}

    return {
        "ruleId": finding.rule_id,
        "level": _LEVEL_BY_SEVERITY[finding.severity],
        "message": {"text": finding.message},
        "locations": [{"physicalLocation": physical_location}],
    }
