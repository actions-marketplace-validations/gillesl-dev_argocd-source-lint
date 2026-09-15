from __future__ import annotations

import fnmatch
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from argocd_source_lint.fsutil import iter_yaml_files, load_yaml_documents
from argocd_source_lint.git_context import local_path_sources
from argocd_source_lint.models import Application, Source

# A Helm chart packaged in the repo: out of scope for v1 content
# interpretation (rendering a chart's templates is delegated to `helm
# template`/a dedicated linter, see DESIGN.md), so we can't know what is
# actually deployed. The whole subtree is treated as covered rather than
# flooding the user with false positives on a directory we can't
# interpret. Kustomize overlays get their own, non-opaque handling below.
_OPAQUE_TOOL_MARKERS = ("Chart.yaml",)

_KUSTOMIZATION_FILENAMES = ("kustomization.yaml", "kustomization.yml", "Kustomization")

# Keys under which `kustomization.yaml` lists a bare relative path (file or
# directory) — resolved and marked covered, recursing into a directory
# that is itself a Kustomize overlay. A remote reference (git URL, SCM
# shorthand) simply won't resolve to anything on disk and is silently
# skipped: verifying it is out of scope, same principle as an external
# `Application` source (see DESIGN.md).
_KUSTOMIZATION_PATH_LIST_KEYS = ("resources", "bases", "components", "crds")


def covered_files_for_source(source_dir: Path, source: Source) -> Iterator[Path]:
    """Files actually covered by a `path` source, aligned with real ArgoCD
    behavior (`directory.recurse`/`include`/`exclude`, see DESIGN.md). Used
    by `orphan-source` and `missing-ignore-diff`."""
    if find_kustomization_file(source_dir) is not None:
        yield from covered_files_for_kustomize_dir(source_dir)
        return

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


def covered_files_for_application(
    app: Application, repo_root: Path, local_origin: str | None
) -> set[Path]:
    """Every file covered by any of `app`'s local `path` sources
    (resolved, absolute) — shared by `missing-ignore-diff` and
    `double-coverage`. `orphan-source` uses this as its base too, layering
    the Helm `$values` file-covering nuance on top (see
    `rules/orphan_source.py`)."""
    covered: set[Path] = set()
    for source in local_path_sources(app, local_origin):
        source_dir = (repo_root / source.path).resolve()
        if not source_dir.is_dir():
            continue
        covered.update(p.resolve() for p in covered_files_for_source(source_dir, source))
    return covered


def is_opaque_tool_directory(source_dir: Path) -> bool:
    return any((source_dir / marker).is_file() for marker in _OPAQUE_TOOL_MARKERS)


def find_kustomization_file(directory: Path) -> Path | None:
    for name in _KUSTOMIZATION_FILENAMES:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def covered_files_for_kustomize_dir(directory: Path, _seen: set[Path] | None = None) -> set[Path]:
    """Files actually consumed by a Kustomize overlay: the
    `kustomization.yaml` itself, plus every local `resources`/`bases`/
    `components`/`crds` entry (recursing into a directory reference),
    every `patches`/`patchesStrategicMerge`/`patchesJson6902` file, and
    every `configMapGenerator`/`secretGenerator` `files`/`envs`/`envFile`
    entry. Anything in the directory but never referenced stays uncovered
    — the same `orphan-source` signal as a plain directory source, one
    level deeper."""
    kustomization_file = find_kustomization_file(directory)
    if kustomization_file is None:
        return set()

    seen = set() if _seen is None else _seen
    resolved_dir = directory.resolve()
    if resolved_dir in seen:
        return set()  # guards against a `resources:` cycle
    seen.add(resolved_dir)

    covered = {kustomization_file.resolve()}
    docs = load_yaml_documents(kustomization_file)
    if not docs:
        return covered
    doc = docs[0]

    for key in _KUSTOMIZATION_PATH_LIST_KEYS:
        for entry in doc.get(key) or []:
            if isinstance(entry, str):
                covered |= _resolve_local_reference(directory, entry, seen)

    for entry in doc.get("patchesStrategicMerge") or []:
        if isinstance(entry, str):  # a dict entry is an inline patch, no file
            covered |= _resolve_local_reference(directory, entry, seen)

    for key in ("patches", "patchesJson6902"):
        for entry in doc.get(key) or []:
            path = (entry or {}).get("path") if isinstance(entry, dict) else None
            if path:
                covered |= _resolve_local_reference(directory, path, seen)

    for generator_key in ("configMapGenerator", "secretGenerator"):
        for generator in doc.get(generator_key) or []:
            covered |= _generator_referenced_files(directory, generator, seen)

    return covered


def _generator_referenced_files(directory: Path, generator: Any, seen: set[Path]) -> set[Path]:
    if not isinstance(generator, dict):
        return set()

    covered: set[Path] = set()
    for file_entry in generator.get("files") or []:
        # A `configMapGenerator`/`secretGenerator` file entry is either a
        # bare path or a `key=path` pair.
        _, _, rel_path = str(file_entry).rpartition("=")
        covered |= _resolve_local_reference(directory, rel_path, seen)

    env_entries = list(generator.get("envs") or [])
    if generator.get("envFile"):
        env_entries.append(generator["envFile"])
    for rel_path in env_entries:
        covered |= _resolve_local_reference(directory, rel_path, seen)

    return covered


def _resolve_local_reference(directory: Path, entry: str, seen: set[Path]) -> set[Path]:
    target = (directory / entry).resolve()
    if target.is_dir():
        return covered_files_for_kustomize_dir(target, seen)
    if target.is_file():
        return {target}
    return set()  # doesn't exist locally: a remote reference, out of scope


def match_directory_patterns(relative_posix: str, pattern: str) -> bool:
    """ArgoCD's `include`/`exclude`: a single glob pattern, or several
    comma-separated ones wrapped in braces (`{a,b}`)."""
    pattern = pattern.strip()
    if pattern.startswith("{") and pattern.endswith("}"):
        alternatives = pattern[1:-1].split(",")
    else:
        alternatives = [pattern]
    return any(fnmatch.fnmatch(relative_posix, alt.strip()) for alt in alternatives)
