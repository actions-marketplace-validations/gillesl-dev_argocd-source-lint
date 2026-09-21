from __future__ import annotations

from pathlib import Path

from argocd_source_lint.git_context import get_origin_url
from argocd_source_lint.loader import RawManifestDiscovery
from argocd_source_lint.models import Finding, Severity
from argocd_source_lint.policy import load_policy
from argocd_source_lint.rules.unknown_sync_option import UnknownSyncOptionRule


def _run_rule(repo_root: Path) -> list[Finding]:
    policy = load_policy(repo_root)
    applications = RawManifestDiscovery().discover(repo_root)
    local_origin = get_origin_url(repo_root)
    return UnknownSyncOptionRule().check(applications, repo_root, policy, local_origin)


_APP_HEADER = """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: web
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: HEAD
    path: manifests/web
  syncPolicy:
"""


def test_wrong_case_key_is_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP_HEADER
            + """\
    syncOptions:
      - respectIgnoreDifferences=true
""",
        }
    )

    findings = _run_rule(repo_root)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "unknown-sync-option"
    assert finding.severity == Severity.WARNING
    assert "respectIgnoreDifferences=true" in finding.message
    assert finding.line == 11


def test_misspelled_key_is_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP_HEADER
            + """\
    syncOptions:
      - PruneLatest=true
""",
        }
    )

    findings = _run_rule(repo_root)

    assert len(findings) == 1
    assert "PruneLatest=true" in findings[0].message


def test_all_known_keys_are_not_flagged(git_repo):
    known_options = [
        "Prune=false",
        "Validate=false",
        "SkipDryRunOnMissingResource=true",
        "Delete=confirm",
        "ApplyOutOfSyncOnly=true",
        "PrunePropagationPolicy=foreground",
        "PruneLast=true",
        "Replace=true",
        "ServerSideApply=true",
        "ClientSideApplyMigration=false",
        "FailOnSharedResource=true",
        "RespectIgnoreDifferences=true",
        "CreateNamespace=true",
    ]
    options_yaml = "".join(f"      - {option}\n" for option in known_options)
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP_HEADER + "    syncOptions:\n" + options_yaml,
        }
    )

    findings = _run_rule(repo_root)

    assert findings == []


def test_no_sync_options_is_not_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: web
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: HEAD
    path: manifests/web
""",
        }
    )

    findings = _run_rule(repo_root)

    assert findings == []


def test_unknown_bare_entry_without_equals_sign_is_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP_HEADER
            + """\
    syncOptions:
      - AutoPrune
""",
        }
    )

    findings = _run_rule(repo_root)

    assert len(findings) == 1
    assert "AutoPrune" in findings[0].message
