from __future__ import annotations

from pathlib import Path

from argocd_source_lint.git_context import get_origin_url
from argocd_source_lint.loader import RawManifestDiscovery
from argocd_source_lint.models import Finding, Severity
from argocd_source_lint.policy import load_policy
from argocd_source_lint.rules.malformed_sync_wave import MalformedSyncWaveRule


def _run_rule(repo_root: Path) -> list[Finding]:
    policy = load_policy(repo_root)
    applications = RawManifestDiscovery().discover(repo_root)
    local_origin = get_origin_url(repo_root)
    return MalformedSyncWaveRule().check(applications, repo_root, policy, local_origin)


_APP = """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: web
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: HEAD
    path: manifests/web
"""


def test_non_numeric_value_is_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP,
            "manifests/web/job.yaml": """\
apiVersion: batch/v1
kind: Job
metadata:
  name: migrate
  annotations:
    argocd.argoproj.io/sync-wave: PreSync
""",
        }
    )

    findings = _run_rule(repo_root)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "malformed-sync-wave"
    assert finding.severity == Severity.WARNING
    assert "PreSync" in finding.message
    assert "Job" in finding.message
    assert "migrate" in finding.message


def test_valid_positive_integer_is_not_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP,
            "manifests/web/job.yaml": """\
apiVersion: batch/v1
kind: Job
metadata:
  name: migrate
  annotations:
    argocd.argoproj.io/sync-wave: "3"
""",
        }
    )

    findings = _run_rule(repo_root)

    assert findings == []


def test_valid_negative_integer_is_not_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP,
            "manifests/web/job.yaml": """\
apiVersion: batch/v1
kind: Job
metadata:
  name: migrate
  annotations:
    argocd.argoproj.io/sync-wave: "-1"
""",
        }
    )

    findings = _run_rule(repo_root)

    assert findings == []


def test_decimal_value_is_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP,
            "manifests/web/job.yaml": """\
apiVersion: batch/v1
kind: Job
metadata:
  name: migrate
  annotations:
    argocd.argoproj.io/sync-wave: "1.5"
""",
        }
    )

    findings = _run_rule(repo_root)

    assert len(findings) == 1
    assert "1.5" in findings[0].message


def test_no_sync_wave_annotation_is_not_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP,
            "manifests/web/deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
""",
        }
    )

    findings = _run_rule(repo_root)

    assert findings == []
