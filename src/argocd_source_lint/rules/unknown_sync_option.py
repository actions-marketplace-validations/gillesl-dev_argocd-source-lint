from __future__ import annotations

from pathlib import Path

from argocd_source_lint.models import Application, Finding, Severity
from argocd_source_lint.policy import Policy
from argocd_source_lint.rules.base import Rule

RULE_ID = "unknown-sync-option"

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


class UnknownSyncOptionRule(Rule):
    """A `syncOptions` entry is matched by ArgoCD as a literal
    `Key=Value` string -- there's no schema validation on it, so a wrong
    case (`respectIgnoreDifferences=true`) or a misspelled key
    (`PruneLatest=true`) is never rejected, just silently a no-op. The
    key portion is checked against the closed, documented set rather
    than the value: the exact accepted values/casing per key are less
    consistently documented, so validating only the key keeps this an
    objective check instead of a guess (same principle as
    `malformed-ignore-diff-pointer`)."""

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
                    findings.append(_finding(app, option, severity))

        return findings


def _finding(app: Application, option: str, severity: Severity) -> Finding:
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
