from __future__ import annotations

from argocd_source_lint import applicationset
from argocd_source_lint.git_context import get_origin_url
from argocd_source_lint.models import Severity
from argocd_source_lint.policy import Policy
from argocd_source_lint.rules.phantom_target import PhantomTargetRule


def _discover(repo_root):
    local_origin = get_origin_url(repo_root)
    return applicationset.discover(repo_root, local_origin, Severity.INFO)


def test_list_generator_expands_one_application_per_element(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/appsets/list-appset.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: list-appset
spec:
  generators:
    - list:
        elements:
          - env: dev
            path: apps/dev
          - env: prod
            path: apps/prod
  template:
    metadata:
      name: 'myapp-{{env}}'
    spec:
      source:
        repoURL: https://example.invalid/repo.git
        targetRevision: HEAD
        path: '{{path}}'
""",
        }
    )

    applications, findings = _discover(repo_root)

    assert findings == []
    assert {app.name for app in applications} == {"myapp-dev", "myapp-prod"}
    paths = {app.sources[0].path for app in applications}
    assert paths == {"apps/dev", "apps/prod"}


def test_git_directories_generator_matches_local_directories(git_repo):
    repo_root = git_repo(
        {
            "apps/foo/deployment.yaml": "kind: Deployment\n",
            "apps/bar/deployment.yaml": "kind: Deployment\n",
            "bootstrap/appsets/dirs-appset.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: dirs-appset
spec:
  generators:
    - git:
        repoURL: https://example.invalid/repo.git
        revision: HEAD
        directories:
          - path: apps/*
  template:
    metadata:
      name: '{{path.basename}}-app'
    spec:
      source:
        repoURL: https://example.invalid/repo.git
        targetRevision: HEAD
        path: '{{path}}'
""",
        }
    )

    applications, findings = _discover(repo_root)

    assert findings == []
    assert {app.name for app in applications} == {"foo-app", "bar-app"}
    assert {app.sources[0].path for app in applications} == {"apps/foo", "apps/bar"}


def test_git_directories_exclude_entry_removes_a_match(git_repo):
    repo_root = git_repo(
        {
            "apps/foo/deployment.yaml": "kind: Deployment\n",
            "apps/baz/deployment.yaml": "kind: Deployment\n",
            "bootstrap/appsets/dirs-appset.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: dirs-appset
spec:
  generators:
    - git:
        repoURL: https://example.invalid/repo.git
        revision: HEAD
        directories:
          - path: apps/*
          - path: apps/baz
            exclude: true
  template:
    metadata:
      name: '{{path.basename}}-app'
    spec:
      source:
        repoURL: https://example.invalid/repo.git
        targetRevision: HEAD
        path: '{{path}}'
""",
        }
    )

    applications, _findings = _discover(repo_root)

    assert {app.name for app in applications} == {"foo-app"}


def test_git_files_generator_reads_and_flattens_json_params(git_repo):
    repo_root = git_repo(
        {
            "clusters/prod.json": '{"cluster": {"name": "prod"}}',
            "bootstrap/appsets/files-appset.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: files-appset
spec:
  generators:
    - git:
        repoURL: https://example.invalid/repo.git
        revision: HEAD
        files:
          - path: clusters/*.json
  template:
    metadata:
      name: 'app-{{cluster.name}}'
    spec:
      source:
        repoURL: https://example.invalid/repo.git
        targetRevision: HEAD
        path: 'manifests/{{cluster.name}}'
""",
        }
    )

    applications, findings = _discover(repo_root)

    assert findings == []
    assert len(applications) == 1
    assert applications[0].name == "app-prod"
    assert applications[0].sources[0].path == "manifests/prod"


def test_matrix_generator_combines_two_child_generators(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/appsets/matrix-appset.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: matrix-appset
spec:
  generators:
    - matrix:
        generators:
          - list:
              elements:
                - region: eu
          - list:
              elements:
                - env: dev
                - env: prod
  template:
    metadata:
      name: 'app-{{region}}-{{env}}'
    spec:
      source:
        repoURL: https://example.invalid/repo.git
        targetRevision: HEAD
        path: manifests/app
""",
        }
    )

    applications, findings = _discover(repo_root)

    assert findings == []
    assert {app.name for app in applications} == {"app-eu-dev", "app-eu-prod"}


def test_unresolvable_generator_produces_info_finding_and_no_applications(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/appsets/clusters-appset.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: clusters-appset
spec:
  generators:
    - clusters: {}
  template:
    metadata:
      name: '{{name}}'
    spec:
      source:
        repoURL: https://example.invalid/repo.git
        targetRevision: HEAD
        path: manifests/app
""",
        }
    )

    applications, findings = _discover(repo_root)

    assert applications == []
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO
    assert findings[0].application == "clusters-appset"
    assert "clusters" in findings[0].message
    assert "cluster/API access" in findings[0].message


def test_go_template_appset_is_flagged_and_skipped_entirely(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/appsets/go-template-appset.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: go-template-appset
spec:
  goTemplate: true
  generators:
    - list:
        elements:
          - env: dev
  template:
    metadata:
      name: 'myapp-{{.env}}'
    spec:
      source:
        repoURL: https://example.invalid/repo.git
        targetRevision: HEAD
        path: manifests/app
""",
        }
    )

    applications, findings = _discover(repo_root)

    assert applications == []
    assert len(findings) == 1
    assert "goTemplate" in findings[0].message


def test_git_generator_on_external_repo_produces_info_finding(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/appsets/external-appset.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: external-appset
spec:
  generators:
    - git:
        repoURL: https://example.invalid/some-other-repo.git
        revision: HEAD
        directories:
          - path: apps/*
  template:
    metadata:
      name: '{{path.basename}}-app'
    spec:
      source:
        repoURL: https://example.invalid/repo.git
        targetRevision: HEAD
        path: '{{path}}'
""",
        }
    )

    applications, findings = _discover(repo_root)

    assert applications == []
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO
    assert "different repo" in findings[0].message


def test_generated_application_is_checked_by_existing_rules(git_repo):
    """The whole point: a generated Application is a plain `Application`
    from the rules' point of view — no special-casing needed in
    phantom-target (or any other rule) to catch a real bug in it."""
    repo_root = git_repo(
        {
            "bootstrap/appsets/list-appset.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: list-appset
spec:
  generators:
    - list:
        elements:
          - env: dev
  template:
    metadata:
      name: 'myapp-{{env}}'
    spec:
      source:
        repoURL: https://example.invalid/repo.git
        targetRevision: HEAD
        path: 'manifests/does-not-exist-{{env}}'
""",
        }
    )
    local_origin = get_origin_url(repo_root)
    applications, appset_findings = applicationset.discover(repo_root, local_origin, Severity.INFO)

    findings = appset_findings + PhantomTargetRule().check(
        applications, repo_root, Policy(), local_origin
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "phantom-target"
    assert findings[0].application == "myapp-dev"
    assert "manifests/does-not-exist-dev" in findings[0].message
