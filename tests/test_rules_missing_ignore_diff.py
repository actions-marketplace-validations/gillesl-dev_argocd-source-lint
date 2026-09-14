from __future__ import annotations

from pathlib import Path

from argocd_source_lint.git_context import get_origin_url
from argocd_source_lint.loader import RawManifestDiscovery
from argocd_source_lint.models import Finding, Severity
from argocd_source_lint.policy import load_policy
from argocd_source_lint.rules.missing_ignore_diff import MissingIgnoreDiffRule


def _run_missing_ignore_diff(repo_root: Path) -> list[Finding]:
    policy = load_policy(repo_root)
    applications = RawManifestDiscovery().discover(repo_root)
    local_origin = get_origin_url(repo_root)
    return MissingIgnoreDiffRule().check(applications, repo_root, policy, local_origin)


def test_good_repo_has_no_findings(fixture_repo):
    repo_root = fixture_repo("good_repo")

    findings = _run_missing_ignore_diff(repo_root)

    assert findings == []


def test_bad_fixture_flags_both_expected_secrets(fixture_repo):
    repo_root = fixture_repo("bad_missing_ignore_diff")

    findings = _run_missing_ignore_diff(repo_root)

    assert len(findings) == 2
    assert all(f.rule_id == "missing-ignore-diff" for f in findings)
    assert all(f.severity == Severity.WARNING for f in findings)  # never error, it's heuristic
    messages = {f.message for f in findings}
    assert any("pg-cluster-app" in m for m in messages)
    assert any("pg-cluster-ca" in m for m in messages)


def test_matching_ignore_diff_by_exact_name_suppresses_finding(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/pg-app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: pg-app
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: HEAD
    path: infrastructure/pg
  syncPolicy:
    automated:
      selfHeal: true
  ignoreDifferences:
    - kind: Secret
      name: pg-cluster-app
    - kind: Secret
      name: pg-cluster-ca
""",
            "infrastructure/pg/cluster.yaml": """\
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: pg-cluster
  namespace: postgres-prod
""",
        }
    )

    findings = _run_missing_ignore_diff(repo_root)

    assert findings == []


def test_nameless_ignore_diff_covers_broadly(git_repo):
    """An `ignoreDifferences` entry with no `name` (a common real-world
    pattern) covers every instance of that `kind`, not just one specific
    name."""
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/pg-app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: pg-app
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: HEAD
    path: infrastructure/pg
  syncPolicy:
    automated:
      selfHeal: true
  ignoreDifferences:
    - kind: Secret
      namespace: postgres-prod
""",
            "infrastructure/pg/cluster.yaml": """\
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: pg-cluster
  namespace: postgres-prod
""",
        }
    )

    findings = _run_missing_ignore_diff(repo_root)

    assert findings == []


def test_ignore_diff_with_mismatched_namespace_does_not_suppress_finding(git_repo):
    """An `ignoreDifferences` rule scoped to a `namespace` different from
    the triggering resource's must not be considered as covering the risk
    (otherwise an `ignoreDifferences` meant for an unrelated Secret with
    the same name would mask the real expected finding)."""
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/pg-app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: pg-app
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: HEAD
    path: infrastructure/pg
  syncPolicy:
    automated:
      selfHeal: true
  ignoreDifferences:
    - kind: Secret
      name: pg-cluster-app
      namespace: unrelated-namespace
""",
            "infrastructure/pg/cluster.yaml": """\
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: pg-cluster
  namespace: postgres-prod
""",
        }
    )

    findings = _run_missing_ignore_diff(repo_root)

    messages = {f.message for f in findings}
    assert any("pg-cluster-app" in m for m in messages)


def test_self_heal_disabled_skips_the_check_entirely(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/pg-app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: pg-app
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: HEAD
    path: infrastructure/pg
""",
            "infrastructure/pg/cluster.yaml": """\
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: pg-cluster
""",
        }
    )

    findings = _run_missing_ignore_diff(repo_root)

    assert findings == []


def test_cert_manager_signature_resolves_name_from_spec_secret_name(git_repo):
    """Verifies that `name_from` generalizes beyond `metadata.name`: for
    cert-manager, the derived Secret's name comes from `spec.secretName`."""
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/tls-app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: tls-app
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: HEAD
    path: infrastructure/tls
  syncPolicy:
    automated:
      selfHeal: true
""",
            "infrastructure/tls/certificate.yaml": """\
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: some-cert
spec:
  secretName: some-cert-tls
""",
        }
    )

    findings = _run_missing_ignore_diff(repo_root)

    assert len(findings) == 1
    assert "some-cert-tls" in findings[0].message


def test_external_source_without_self_heal_produces_no_finding_at_all(git_repo):
    """selfHeal disabled entirely disarms the rule: it must say nothing at
    all, not even an `info` "out of scope", about an external source of an
    Application where the risk it checks can't occur anyway."""
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/external-app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: external-app
spec:
  source:
    repoURL: https://example.invalid/some-other-repo.git
    targetRevision: HEAD
    path: never/checked
""",
        }
    )

    findings = _run_missing_ignore_diff(repo_root)

    assert findings == []


def test_multi_repo_application_is_flagged_info_and_not_checked(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/external-app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: external-app
spec:
  source:
    repoURL: https://example.invalid/some-other-repo.git
    targetRevision: HEAD
    path: never/checked
  syncPolicy:
    automated:
      selfHeal: true
""",
        }
    )

    findings = _run_missing_ignore_diff(repo_root)

    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO
    assert findings[0].application == "external-app"


def test_rule_severity_is_configurable_via_policy(fixture_repo):
    repo_root = fixture_repo("bad_missing_ignore_diff")
    (repo_root / ".argocd-lint.yaml").write_text(
        "rules:\n  missing-ignore-diff: error\n",
        encoding="utf-8",
    )

    findings = _run_missing_ignore_diff(repo_root)

    assert len(findings) == 2
    assert all(f.severity == Severity.ERROR for f in findings)


def test_custom_known_operator_from_policy_is_merged_with_builtin_pack(git_repo):
    repo_root = git_repo(
        {
            ".argocd-lint.yaml": """\
known_operators:
  - crd_trigger: acme.internal/WidgetCluster
    name_from: metadata.name
    expect_ignore_on:
      - kind: Secret
        name_pattern: "{name}-credentials"
""",
            "bootstrap/argocd-apps/widget-app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: widget-app
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: HEAD
    path: infrastructure/widget
  syncPolicy:
    automated:
      selfHeal: true
""",
            "infrastructure/widget/cluster.yaml": """\
apiVersion: acme.internal/v1
kind: WidgetCluster
metadata:
  name: my-widget
""",
        }
    )

    findings = _run_missing_ignore_diff(repo_root)

    assert len(findings) == 1
    assert "my-widget-credentials" in findings[0].message
