from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Must match the `repoURL` declared in the fixtures' Application manifests
# so they are classified as mono-repo (see DESIGN.md).
DEFAULT_ORIGIN_URL = "https://example.invalid/repo.git"


def _run_git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_git_repo(repo_root: Path, origin_url: str) -> None:
    _run_git("init", "-q", cwd=repo_root)
    _run_git("config", "user.email", "test@example.com", cwd=repo_root)
    _run_git("config", "user.name", "Test", cwd=repo_root)
    _run_git("remote", "add", "origin", origin_url, cwd=repo_root)
    _run_git("add", "-A", cwd=repo_root)
    _run_git("commit", "-q", "-m", "initial", cwd=repo_root)


@pytest.fixture
def git_repo(tmp_path: Path) -> Callable[..., Path]:
    """Builds a real mini Git repo in tmp_path from a {relative path:
    content} mapping, with an `origin` remote (no filesystem mocks — a
    real `git init` as a fixture)."""

    def _make(files: dict[str, str], origin_url: str = DEFAULT_ORIGIN_URL) -> Path:
        repo_root = tmp_path
        for relative_path, content in files.items():
            file_path = repo_root / relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
        _init_git_repo(repo_root, origin_url)
        return repo_root

    return _make


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Callable[..., Path]:
    """Copies tests/fixtures/<name>/ into tmp_path and turns it into a real
    Git repo (same default `origin` remote as `git_repo`)."""

    def _make(name: str, origin_url: str = DEFAULT_ORIGIN_URL) -> Path:
        source_dir = FIXTURES_DIR / name
        repo_root = tmp_path
        shutil.copytree(source_dir, repo_root, dirs_exist_ok=True)
        _init_git_repo(repo_root, origin_url)
        return repo_root

    return _make
