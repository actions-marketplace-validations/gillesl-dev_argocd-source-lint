from __future__ import annotations

from pathlib import Path

from argocd_source_lint.git_context import get_origin_url
from argocd_source_lint.loader import RawManifestDiscovery
from argocd_source_lint.models import Finding, Severity
from argocd_source_lint.policy import load_policy
from argocd_source_lint.rules.malformed_ignore_diff_jq_expression import (
    MalformedIgnoreDiffJqExpressionRule,
)


def _run_rule(repo_root: Path) -> list[Finding]:
    policy = load_policy(repo_root)
    applications = RawManifestDiscovery().discover(repo_root)
    local_origin = get_origin_url(repo_root)
    return MalformedIgnoreDiffJqExpressionRule().check(
        applications, repo_root, policy, local_origin
    )


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
"""


def test_jsonpointer_style_expression_is_flagged(git_repo):
    """The exact confusion this rule targets: a `jsonPointers`-style
    leading-slash path pasted into the sibling `jqPathExpressions`
    field."""
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP_HEADER
            + """\
  ignoreDifferences:
    - group: apps
      kind: Deployment
      name: web
      jqPathExpressions:
        - /spec/replicas
""",
        }
    )

    findings = _run_rule(repo_root)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "malformed-ignore-diff-jq-expression"
    assert finding.severity == Severity.WARNING
    assert "/spec/replicas" in finding.message
    assert "doesn't start with `.`" in finding.message
    assert finding.line == 10


def test_well_formed_jq_expression_is_not_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP_HEADER
            + """\
  ignoreDifferences:
    - group: apps
      kind: Deployment
      name: web
      jqPathExpressions:
        - .spec.replicas
""",
        }
    )

    findings = _run_rule(repo_root)

    assert findings == []


def test_well_formed_filter_expression_is_not_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP_HEADER
            + """\
  ignoreDifferences:
    - group: apps
      kind: Deployment
      name: web
      jqPathExpressions:
        - '.spec.template.spec.initContainers[] | select(.name == "injected")'
""",
        }
    )

    findings = _run_rule(repo_root)

    assert findings == []


def test_no_ignore_differences_is_not_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP_HEADER,
        }
    )

    findings = _run_rule(repo_root)

    assert findings == []


def test_multiple_malformed_expressions_across_rules_are_each_flagged(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/web.yaml": _APP_HEADER
            + """\
  ignoreDifferences:
    - group: apps
      kind: Deployment
      name: web
      jqPathExpressions:
        - /spec/replicas
    - kind: Service
      name: web
      jqPathExpressions:
        - /spec/ports
""",
        }
    )

    findings = _run_rule(repo_root)

    assert len(findings) == 2
    messages = {f.message for f in findings}
    assert any("/spec/replicas" in m for m in messages)
    assert any("/spec/ports" in m for m in messages)
