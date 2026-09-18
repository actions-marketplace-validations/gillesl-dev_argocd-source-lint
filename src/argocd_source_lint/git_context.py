from __future__ import annotations

import re
import subprocess
from pathlib import Path

from argocd_source_lint.models import Application, Source

_SCP_LIKE_RE = re.compile(r"^(?:[^@/]+@)?([^:/]+):(.+)$")


def get_origin_url(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    return result.stdout.strip() or None


def normalize_repo_url(url: str) -> str:
    """Reduces a Git URL (https, ssh://, or scp-like git@host:path) to
    `host/path` in lowercase, without a port or `.git` suffix, so that
    different forms of the same URL can be compared against each other."""
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[: -len(".git")]

    if "://" in url:
        url = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", url)
        url = re.sub(r"^[^@/]+@", "", url)
        # Explicit port on the host (e.g. ssh://git@host:2222/...) must not
        # make this diverge from the equivalent scp-like form
        # (git@host:path), which never carries a port.
        url = re.sub(r"^([^/]+):\d+(/|$)", r"\1\2", url)
    else:
        match = _SCP_LIKE_RE.match(url)
        if match:
            host, path = match.groups()
            url = f"{host}/{path}"

    return url.lower().rstrip("/")


def is_local_repo_url(repo_url: str, local_origin: str | None) -> bool:
    if not repo_url or not local_origin:
        return False
    return normalize_repo_url(repo_url) == normalize_repo_url(local_origin)


def local_path_sources(app: Application, local_origin: str | None) -> list[Source]:
    """Sources with a `path` (not just a `chart`) whose repoURL matches the
    local repo. Chart-only sources (Helm repo) are excluded outright: they
    never have any files to resolve locally."""
    return [
        source
        for source in app.sources
        if source.path is not None and is_local_repo_url(source.repo_url, local_origin)
    ]


def external_path_sources(app: Application, local_origin: str | None) -> list[Source]:
    """Sources with a `path` that points to a Git repo different from the
    local repo (see DESIGN.md "Mono-repo v1 scope") — the "out of scope
    v1" counterpart to `local_path_sources`. An Application can have
    sources in both lists at once (mixed external chart + local manifests
    pattern): each rule must report these sources as `info` individually,
    without skipping verification of its local sources."""
    return [
        source
        for source in app.sources
        if source.path is not None and not is_local_repo_url(source.repo_url, local_origin)
    ]


def is_revision_resolvable(repo_root: Path, revision: str) -> bool:
    """Shallow-clone safeguard (see DESIGN.md "The unverifiable severity"):
    a revision not fetched locally must never be treated as "path
    missing" — only as unverifiable. Used by `phantom-target` and
    `broken-values-ref`."""
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
    )
    return result.returncode == 0


def _resolve_commit(repo_root: Path, revision: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", f"{revision}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def revision_matches_checkout(repo_root: Path, revision: str) -> bool | None:
    """Whether `revision` resolves to the same commit as the current
    checkout (`HEAD`) — used by `revision-mismatch` (see DESIGN.md
    "orphan-source, missing-ignore-diff and double-coverage read the
    working tree, not `targetRevision`"). `None` when `revision` isn't
    resolvable at all: that's already `phantom-target`'s/
    `broken-values-ref`'s shallow-clone case (`is_revision_resolvable`),
    not a mismatch to report a second time."""
    target = _resolve_commit(repo_root, revision)
    if target is None:
        return None
    head = _resolve_commit(repo_root, "HEAD")
    return head is not None and head == target


def list_tree_paths(repo_root: Path, revision: str, pathspec: str) -> list[str]:
    """File paths under `pathspec` at `revision`. Assumes `revision` is
    already known to be resolvable (`is_revision_resolvable`) — otherwise
    returns an empty list instead of failing loudly."""
    result = subprocess.run(
        ["git", "ls-tree", "-r", revision, "--name-only", "--", pathspec],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()
