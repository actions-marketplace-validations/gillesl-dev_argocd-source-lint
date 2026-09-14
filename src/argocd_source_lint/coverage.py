from __future__ import annotations

import fnmatch
from collections.abc import Iterator
from pathlib import Path

from argocd_source_lint.fsutil import iter_yaml_files
from argocd_source_lint.models import Source

# Markers of a directory rendered by another tool (Helm chart packaged in
# the repo, Kustomize overlay): out of scope for v1 content interpretation
# (Kustomize is delegated to kustomize-lint, see DESIGN.md), so we can't
# know what is actually deployed. The whole subtree is treated as covered
# rather than flooding the user with false positives on a directory we
# can't interpret.
_OPAQUE_TOOL_MARKERS = ("kustomization.yaml", "kustomization.yml", "Chart.yaml")


def covered_files_for_source(source_dir: Path, source: Source) -> Iterator[Path]:
    """Files actually covered by a `path` source, aligned with real ArgoCD
    behavior (`directory.recurse`/`include`/`exclude`, see DESIGN.md). Used
    by `orphan-source` and `missing-ignore-diff`."""
    if is_opaque_tool_directory(source_dir):
        yield from iter_yaml_files(source_dir)
        return

    for candidate in iter_yaml_files(source_dir, recurse=source.directory_recurse):
        relative = candidate.relative_to(source_dir).as_posix()
        if source.directory_include and not match_directory_patterns(
            relative, source.directory_include
        ):
            continue
        if source.directory_exclude and match_directory_patterns(
            relative, source.directory_exclude
        ):
            continue
        yield candidate


def is_opaque_tool_directory(source_dir: Path) -> bool:
    return any((source_dir / marker).is_file() for marker in _OPAQUE_TOOL_MARKERS)


def match_directory_patterns(relative_posix: str, pattern: str) -> bool:
    """ArgoCD's `include`/`exclude`: a single glob pattern, or several
    comma-separated ones wrapped in braces (`{a,b}`)."""
    pattern = pattern.strip()
    if pattern.startswith("{") and pattern.endswith("}"):
        alternatives = pattern[1:-1].split(",")
    else:
        alternatives = [pattern]
    return any(fnmatch.fnmatch(relative_posix, alt.strip()) for alt in alternatives)
