from __future__ import annotations

import hashlib
import json

from argocd_source_lint.models import Finding, Severity

# GitLab's "Code Quality" format (derived from CodeClimate) — NOT SARIF.
# Confirmed against the official GitLab docs before implementing: SARIF
# and GitLab Code Quality are two distinct schemas (see DESIGN.md).
_SEVERITY_BY_SEVERITY = {
    Severity.ERROR: "major",
    Severity.WARNING: "minor",
    Severity.INFO: "info",
    Severity.UNVERIFIABLE: "major",
}


def render_findings(findings: list[Finding]) -> str:
    payload = [_issue(finding) for finding in findings]
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _issue(finding: Finding) -> dict:
    path = finding.file.as_posix()
    line = finding.line or 1
    return {
        "description": finding.message,
        "check_name": finding.rule_id,
        "fingerprint": _fingerprint(finding),
        "severity": _SEVERITY_BY_SEVERITY[finding.severity],
        "location": {
            "path": path,
            "lines": {"begin": line},
        },
    }


def _fingerprint(finding: Finding) -> str:
    identity = (
        f"{finding.rule_id}|{finding.file.as_posix()}|{finding.application}|{finding.message}"
    )
    return hashlib.md5(identity.encode("utf-8")).hexdigest()
