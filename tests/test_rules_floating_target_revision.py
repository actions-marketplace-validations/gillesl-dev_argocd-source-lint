from __future__ import annotations

from pathlib import Path

from argocd_source_lint.git_context import get_origin_url
from argocd_source_lint.loader import RawManifestDiscovery
from argocd_source_lint.models import Finding, Severity
from argocd_source_lint.policy import load_policy
from argocd_source_lint.rules.floating_target_revision import FloatingTargetRevisionRule


def _run_rule(repo_root: Path) -> list[Finding]:
    policy = load_policy(repo_root)
    applications = RawManifestDiscovery().discover(repo_root)
    local_origin = get_origin_url(repo_root)
    return FloatingTargetRevisionRule().check(applications, repo_root, policy, local_origin)


def _app(name: str, target_revision: str, *, chart: str | None = None) -> str:
    source = f"    chart: {chart}\n" if chart else "    path: manifests/app\n"
    return f"""\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {name}
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: "{target_revision}"
{source}"""


def test_exact_version_pin_is_not_flagged(git_repo):
    repo_root = git_repo({"bootstrap/argocd-apps/web.yaml": _app("web", "1.2.0", chart="my-chart")})

    assert _run_rule(repo_root) == []


def test_branch_name_is_not_flagged(git_repo):
    repo_root = git_repo({"bootstrap/argocd-apps/web.yaml": _app("web", "main")})

    assert _run_rule(repo_root) == []


def test_head_is_not_flagged(git_repo):
    repo_root = git_repo({"bootstrap/argocd-apps/web.yaml": _app("web", "HEAD")})

    assert _run_rule(repo_root) == []


def test_commit_sha_is_not_flagged(git_repo):
    repo_root = git_repo(
        {"bootstrap/argocd-apps/web.yaml": _app("web", "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2")}
    )

    assert _run_rule(repo_root) == []


def test_bare_wildcard_is_flagged(git_repo):
    repo_root = git_repo({"bootstrap/argocd-apps/web.yaml": _app("web", "*", chart="my-chart")})

    findings = _run_rule(repo_root)

    assert len(findings) == 1
    assert findings[0].rule_id == "floating-target-revision"
    assert findings[0].severity == Severity.WARNING
    assert "targetRevision: *" in findings[0].message


def test_patch_range_is_flagged(git_repo):
    repo_root = git_repo({"bootstrap/argocd-apps/web.yaml": _app("web", "1.2.*", chart="my-chart")})

    findings = _run_rule(repo_root)

    assert len(findings) == 1
    assert "1.2.*" in findings[0].message


def test_compound_range_is_flagged(git_repo):
    repo_root = git_repo(
        {"bootstrap/argocd-apps/web.yaml": _app("web", ">=1.2.0 <1.3.0", chart="my-chart")}
    )

    findings = _run_rule(repo_root)

    assert len(findings) == 1


def test_chart_source_message_mentions_chart_version(git_repo):
    repo_root = git_repo({"bootstrap/argocd-apps/web.yaml": _app("web", "*", chart="my-chart")})

    findings = _run_rule(repo_root)

    assert "chart version" in findings[0].message


def test_git_path_source_message_mentions_git_tag(git_repo):
    repo_root = git_repo({"bootstrap/argocd-apps/web.yaml": _app("web", "^1.0.0")})

    findings = _run_rule(repo_root)

    assert "Git tag" in findings[0].message


def test_external_source_is_still_flagged(git_repo):
    """Unlike most rules, this one needs no local repository access: the
    string itself is already visible in the Application manifest, so an
    external source is checked just the same, not marked out of scope."""
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _app("web", "*", chart="my-chart"),
        },
        origin_url="https://example.invalid/a-different-repo.git",
    )

    findings = _run_rule(repo_root)

    assert len(findings) == 1
    assert findings[0].rule_id == "floating-target-revision"
