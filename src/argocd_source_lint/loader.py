from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from argocd_source_lint.fsutil import iter_yaml_files, load_yaml_documents
from argocd_source_lint.models import Application, IgnoreDiffRule, Source


class ApplicationDiscovery(ABC):
    @abstractmethod
    def discover(self, repo_root: Path) -> list[Application]: ...


class RawManifestDiscovery(ApplicationDiscovery):
    """Walks YAML files containing `kind: Application`. Files that don't
    parse as valid YAML (e.g. Helm templates using Go syntax) are silently
    skipped: they aren't raw Application manifests anyway."""

    def discover(self, repo_root: Path) -> list[Application]:
        applications: list[Application] = []
        for manifest_path in sorted(iter_yaml_files(repo_root)):
            for doc in load_yaml_documents(manifest_path):
                if _is_argocd_application(doc):
                    applications.append(_build_application(doc, manifest_path, repo_root))
        return applications


def _is_argocd_application(doc: dict[str, Any]) -> bool:
    return doc.get("kind") == "Application" and str(doc.get("apiVersion", "")).startswith(
        "argoproj.io/"
    )


def _build_application(doc: dict[str, Any], manifest_path: Path, repo_root: Path) -> Application:
    metadata = doc.get("metadata", {}) or {}
    spec = doc.get("spec", {}) or {}

    raw_sources: list[dict[str, Any]]
    if "sources" in spec:
        raw_sources = spec["sources"] or []
    elif "source" in spec:
        raw_sources = [spec["source"]]
    else:
        raw_sources = []

    sources = [_build_source(raw) for raw in raw_sources]

    self_heal = bool(((spec.get("syncPolicy") or {}).get("automated") or {}).get("selfHeal", False))

    ignore_differences = [
        _build_ignore_diff_rule(raw) for raw in spec.get("ignoreDifferences", []) or []
    ]

    try:
        source_file = manifest_path.relative_to(repo_root)
    except ValueError:
        source_file = manifest_path

    return Application(
        name=metadata.get("name", ""),
        namespace=metadata.get("namespace") or "argocd",
        sources=sources,
        sync_policy_self_heal=self_heal,
        ignore_differences=ignore_differences,
        source_file=source_file,
    )


def _build_source(raw: dict[str, Any]) -> Source:
    helm = raw.get("helm") or {}
    directory = raw.get("directory") or {}
    return Source(
        repo_url=raw.get("repoURL", ""),
        target_revision=raw.get("targetRevision") or "HEAD",
        path=raw.get("path"),
        chart=raw.get("chart"),
        ref=raw.get("ref"),
        helm_value_files=helm.get("valueFiles", []) or [],
        directory_recurse=bool(directory.get("recurse", False)),
        directory_include=directory.get("include"),
        directory_exclude=directory.get("exclude"),
    )


def _build_ignore_diff_rule(raw: dict[str, Any]) -> IgnoreDiffRule:
    return IgnoreDiffRule(
        group=raw.get("group"),
        kind=raw.get("kind", ""),
        name=raw.get("name"),
        namespace=raw.get("namespace"),
        json_pointers=raw.get("jsonPointers", []) or [],
        jq_path_expressions=raw.get("jqPathExpressions", []) or [],
        managed_fields_managers=raw.get("managedFieldsManagers", []) or [],
    )
