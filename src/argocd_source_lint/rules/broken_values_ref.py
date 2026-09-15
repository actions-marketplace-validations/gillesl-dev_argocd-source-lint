from __future__ import annotations

from pathlib import Path

from argocd_source_lint.git_context import (
    is_local_repo_url,
    is_revision_resolvable,
    list_tree_paths,
)
from argocd_source_lint.models import Application, Finding, Severity
from argocd_source_lint.policy import Policy
from argocd_source_lint.rules.base import Rule

RULE_ID = "broken-values-ref"


class BrokenValuesRefRule(Rule):
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
        tree_paths: dict[str, set[str]] = {}

        for app in applications:
            ref_sources = {source.ref: source for source in app.sources if source.ref}

            for source in app.sources:
                for idx, entry in enumerate(source.helm_value_files):
                    ref_name, rel_path = _parse_ref_entry(entry)
                    if ref_name is None:
                        continue  # not a `$ref/...` entry: out of scope for this rule

                    entry_line = (
                        source.helm_value_files_lines[idx]
                        if idx < len(source.helm_value_files_lines)
                        else None
                    )

                    ref_source = ref_sources.get(ref_name)
                    if ref_source is None:
                        findings.append(
                            _finding(
                                app,
                                severity,
                                f"`{entry}` references `$ref: {ref_name}`, but no source "
                                f"of the Application declares `ref: {ref_name}`.",
                                line=entry_line,
                            )
                        )
                        continue

                    if not is_local_repo_url(ref_source.repo_url, local_origin):
                        findings.append(
                            _finding(
                                app,
                                Severity.INFO,
                                f"`{entry}`: the `ref: {ref_name}` source points to an "
                                "external repo — out of scope v1, this tool only "
                                "verifies sources in the repo it runs in, see DESIGN.md.",
                                line=entry_line,
                            )
                        )
                        continue

                    revision = ref_source.target_revision
                    if revision not in revision_resolvable:
                        revision_resolvable[revision] = is_revision_resolvable(repo_root, revision)

                    if not revision_resolvable[revision]:
                        findings.append(
                            _finding(
                                app,
                                Severity.UNVERIFIABLE,
                                f"`{entry}`: revision `{revision}` (source `ref: "
                                f"{ref_name}`) missing from the local checkout — unable "
                                "to verify the file. Add `fetch-depth: 0` or fetch the "
                                "branch in question in CI.",
                                line=entry_line,
                            )
                        )
                        continue

                    if rel_path not in _tree_paths(repo_root, revision, tree_paths):
                        findings.append(
                            _finding(
                                app,
                                severity,
                                f"`{entry}`: file `{rel_path}` not found at revision "
                                f"`{revision}` (source `ref: {ref_name}`).",
                                line=entry_line,
                            )
                        )

        return findings


def _tree_paths(repo_root: Path, revision: str, cache: dict[str, set[str]]) -> set[str]:
    """Lists the files of a revision only once (cached), instead of one
    `git ls-tree` call per referenced `$ref/path.yaml` entry."""
    if revision not in cache:
        cache[revision] = set(list_tree_paths(repo_root, revision, "."))
    return cache[revision]


def _parse_ref_entry(entry: str) -> tuple[str | None, str]:
    if not entry.startswith("$"):
        return None, ""
    ref_name, separator, rel_path = entry[1:].partition("/")
    if not separator:
        return None, ""
    return ref_name, rel_path


def _finding(
    app: Application, severity: Severity, message: str, line: int | None = None
) -> Finding:
    return Finding(
        rule_id=RULE_ID,
        severity=severity,
        application=app.name,
        message=message,
        file=app.source_file,
        line=line,
    )
