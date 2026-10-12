from __future__ import annotations

from pathlib import Path

from argocd_source_lint.models import Application, Finding, Severity
from argocd_source_lint.policy import Policy
from argocd_source_lint.rules.base import Rule

RULE_ID = "floating-target-revision"

# Confirmed against the official ArgoCD docs (Tracking and Deployment
# Strategies): a `targetRevision` that mixes in any of these characters is
# read as a semver constraint, never as a plain tag, branch, or commit SHA.
# A real ref name can never contain them in the first place; `git
# check-ref-format` forbids `*`, `~`, `^`, and whitespace outright. Their
# presence is therefore a confirmed signal, not a guess. `^`/`~` also show
# up in ArgoCD's own OCI registry semver constraint docs, alongside Helm's.
_FLOATING_CHARACTERS = set("*^~<>=")


class FloatingTargetRevisionRule(Rule):
    """ArgoCD resolves a `targetRevision` written as a semver constraint
    (`1.2.*`, `>=1.2.0 <1.3.0`, `*`) against whatever chart versions or Git
    tags exist at sync time, picking the highest match. The same
    Application can then deploy different content tomorrow with no
    corresponding commit in this repository, the opposite of what Git
    history is supposed to guarantee. An exact pin (a plain version, tag,
    branch, or commit SHA) never has this problem, so only constraint
    syntax is flagged here. Applies to every source regardless of whether
    it points at this repo or another one: the string itself is already
    visible in the Application manifest either way."""

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
            for source in app.sources:
                revision = source.target_revision
                if not _FLOATING_CHARACTERS.intersection(revision):
                    continue

                kind = "chart version" if source.chart else "Git tag"
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        severity=severity,
                        application=app.name,
                        message=(
                            f"`targetRevision: {revision}` is a version range, not an exact "
                            f"pin. ArgoCD resolves it against the highest matching {kind} at "
                            "every sync, so the deployed content can change with no "
                            "corresponding commit in this repository."
                        ),
                        file=app.source_file,
                        line=source.line,
                    )
                )

        return findings
