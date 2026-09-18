from __future__ import annotations

import pytest

from argocd_source_lint.git_context import (
    is_local_repo_url,
    normalize_repo_url,
    revision_matches_checkout,
)

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
