from __future__ import annotations

from pathlib import Path

from argocd_source_lint.git_context import (
    external_path_sources,
    is_revision_resolvable,
    list_tree_paths,
    local_path_sources,
)
from argocd_source_lint.models import Application, Finding, Severity
from argocd_source_lint.policy import Policy
from argocd_source_lint.rules.base import Rule, external_source_finding

RULE_ID = "phantom-target"


class PhantomTargetRule(Rule):
    rule_id = RULE_ID

    def check(
        self,
        applications: list[Application],
        repo_root: Path,
        policy: Policy,
        local_origin: str | None,
    ) -> list[Finding]:
        severity = policy.rules.get(RULE_ID, Severity.ERROR)
        findings: list[Finding] = []
        revision_resolvable: dict[str, bool] = {}
        target_exists: dict[tuple[str, str], bool] = {}

        for app in applications:
            for source in external_path_sources(app, local_origin):
                findings.append(external_source_finding(RULE_ID, app, source))

            for source in local_path_sources(app, local_origin):
                revision = source.target_revision
                if revision not in revision_resolvable:
                    revision_resolvable[revision] = is_revision_resolvable(repo_root, revision)

                if not revision_resolvable[revision]:
                    findings.append(
                        Finding(
                            rule_id=RULE_ID,
                            severity=Severity.UNVERIFIABLE,
                            application=app.name,
                            message=(
                                f"Revision `{revision}` missing from the local checkout — "
                                "unable to verify the path. Add `fetch-depth: 0` or fetch "
                                "the branch in question in CI."
                            ),
                            file=app.source_file,
                            line=source.line,
                        )
                    )
                    continue

                pathspec = source.path.strip("/") or "."
                key = (revision, pathspec)
                if key not in target_exists:
                    target_exists[key] = bool(list_tree_paths(repo_root, revision, pathspec))

                if not target_exists[key]:
                    findings.append(
                        Finding(
                            rule_id=RULE_ID,
                            severity=severity,
                            application=app.name,
                            message=(
                                f"path `{source.path}` not found at revision "
                                f"`{revision}` — phantom target."
                            ),
                            file=app.source_file,
                            line=source.line,
                        )
                    )

        return findings
