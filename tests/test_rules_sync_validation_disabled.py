from __future__ import annotations

from pathlib import Path

from argocd_source_lint.git_context import get_origin_url
from argocd_source_lint.loader import RawManifestDiscovery
from argocd_source_lint.models import Finding, Severity
from argocd_source_lint.policy import load_policy
from argocd_source_lint.rules.sync_validation_disabled import SyncValidationDisabledRule


def _run_rule(repo_root: Path) -> list[Finding]:
    policy = load_policy(repo_root)
    applications = RawManifestDiscovery().discover(repo_root)
    local_origin = get_origin_url(repo_root)
    return SyncValidationDisabledRule().check(applications, repo_root, policy, local_origin)


def test_validate_false_is_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: app
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: HEAD
    path: manifests/app
  syncPolicy:
    syncOptions:
      - Validate=false
""",
        }
    )

    findings = _run_rule(repo_root)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "sync-validation-disabled"
    assert finding.severity == Severity.INFO
    assert "Validate=false" in finding.message
    assert finding.line == 11


def test_no_sync_options_is_not_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: app
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: HEAD
    path: manifests/app
""",
        }
    )

    findings = _run_rule(repo_root)

    assert findings == []


def test_other_sync_options_without_validate_false_are_not_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: app
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: HEAD
    path: manifests/app
  syncPolicy:
    syncOptions:
      - CreateNamespace=true
      - RespectIgnoreDifferences=true
""",
        }
    )

    findings = _run_rule(repo_root)

    assert findings == []
