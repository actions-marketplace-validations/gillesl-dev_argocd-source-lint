from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from argocd_source_lint.git_context import (
    clear_caches,
    is_git_available,
    is_local_repo_url,
    normalize_repo_url,
    revision_matches_checkout,
)


def test_is_git_available_true_when_git_is_on_path():
    assert is_git_available() is True


def test_is_git_available_false_when_git_is_missing():
    with patch("shutil.which", return_value=None):
        assert is_git_available() is False


EQUIVALENT_FORMS = [
    "https://gitlab.example.com/group/example-repo.git",
    "https://gitlab.example.com/group/example-repo",
    "https://gitlab.example.com/group/example-repo.git/",
    "ssh://git@gitlab.example.com/group/example-repo.git",
    "ssh://git@gitlab.example.com:22/group/example-repo.git",
    "git@gitlab.example.com:group/example-repo.git",
]


@pytest.mark.parametrize("url", EQUIVALENT_FORMS)
def test_equivalent_url_forms_normalize_identically(url: str):
    assert normalize_repo_url(url) == "gitlab.example.com/group/example-repo"


@pytest.mark.parametrize("url", EQUIVALENT_FORMS)
def test_is_local_repo_url_matches_across_forms(url: str):
    local_origin = "git@gitlab.example.com:group/example-repo.git"
    assert is_local_repo_url(url, local_origin) is True


def test_is_local_repo_url_rejects_different_repo():
    assert (
        is_local_repo_url(
            "https://gitlab.example.com/group/other-repo.git",
            "git@gitlab.example.com:group/example-repo.git",
        )
        is False
    )


def test_is_local_repo_url_handles_missing_origin():
    assert is_local_repo_url("https://gitlab.example.com/group/example-repo.git", None) is False


def test_revision_matches_checkout_true_for_head(git_repo):
    repo_root = git_repo({"a.txt": "x"})
    assert revision_matches_checkout(repo_root, "HEAD") is True


def test_revision_matches_checkout_false_for_a_diverged_tag(git_repo, git_tag, git_commit):
    repo_root = git_repo({"a.txt": "x"})
    git_tag(repo_root, "v1.0")
    git_commit(repo_root, {})
    assert revision_matches_checkout(repo_root, "v1.0") is False


def test_revision_matches_checkout_none_for_unresolvable_revision(git_repo):
    repo_root = git_repo({"a.txt": "x"})
    assert revision_matches_checkout(repo_root, "does-not-exist-anywhere") is None


def test_resolve_commit_is_cached_across_repeated_calls(git_repo):
    """50 Applications sharing `targetRevision: HEAD`, each checked by
    several local-source rules, cost 702 identical `git rev-parse`
    calls before this cache existed (~58s on Windows, where subprocess
    spawn itself dominates) -- confirmed for real, not estimated."""
    repo_root = git_repo({"a.txt": "x"})
    clear_caches()

    with patch("subprocess.run", wraps=subprocess.run) as spy:
        for _ in range(5):
            assert revision_matches_checkout(repo_root, "HEAD") is True

    rev_parse_calls = [c for c in spy.call_args_list if c.args[0][:2] == ["git", "rev-parse"]]
    assert len(rev_parse_calls) == 1  # not 10 (2 per call: revision + HEAD, x5 calls)


def test_clear_caches_picks_up_a_new_commit(git_repo, git_tag, git_commit):
    """The one scenario the cache must never get wrong: a repo mutated
    between two `argocd-source-lint` invocations that happen to share
    a process (only possible in a test harness calling the CLI twice
    in-process -- a real run is always a fresh OS process)."""
    repo_root = git_repo({"a.txt": "x"})
    git_tag(repo_root, "v1.0")
    clear_caches()
    assert revision_matches_checkout(repo_root, "v1.0") is True  # HEAD == v1.0 right now

    git_commit(repo_root, {})  # HEAD moves past v1.0
    clear_caches()

    assert revision_matches_checkout(repo_root, "v1.0") is False
