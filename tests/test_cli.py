from __future__ import annotations

import json

from typer.testing import CliRunner

from argocd_source_lint.cli import app

runner = CliRunner()


def test_exit_code_1_on_phantom_target_error(fixture_repo):
    repo_root = fixture_repo("bad_phantom_target")

    result = runner.invoke(app, [str(repo_root)])

    assert result.exit_code == 1


def test_exit_code_0_on_good_repo(fixture_repo):
    repo_root = fixture_repo("good_repo")

    result = runner.invoke(app, [str(repo_root)])

    assert result.exit_code == 0


def test_unverifiable_blocks_ci_by_default(git_repo):
    repo_root = git_repo(
        {
            "bootstrap/argocd-apps/demo-app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: demo-app
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: never-fetched-branch
    path: manifests/demo-app
""",
            "manifests/demo-app/deployment.yaml": "kind: Deployment\n",
        }
    )

    result = runner.invoke(app, [str(repo_root)])

    assert result.exit_code == 1


def test_unverifiable_blocks_ci_false_makes_it_non_blocking(git_repo):
    repo_root = git_repo(
        {
            ".argocd-lint.yaml": "unverifiable_blocks_ci: false\n",
            "bootstrap/argocd-apps/demo-app.yaml": """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: demo-app
spec:
  source:
    repoURL: https://example.invalid/repo.git
    targetRevision: never-fetched-branch
    path: manifests/demo-app
""",
            "manifests/demo-app/deployment.yaml": "kind: Deployment\n",
        }
    )

    result = runner.invoke(app, [str(repo_root)])

    assert result.exit_code == 0


def test_json_format_prints_to_stdout(fixture_repo):
    repo_root = fixture_repo("bad_phantom_target")

    result = runner.invoke(app, [str(repo_root), "--format", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert len(payload["findings"]) == 1
    assert payload["findings"][0]["rule_id"] == "phantom-target"


def test_sarif_format_writes_to_output_file(fixture_repo, tmp_path):
    repo_root = fixture_repo("bad_phantom_target")
    output_file = tmp_path / "results.sarif"

    result = runner.invoke(app, [str(repo_root), "--format", "sarif", "--output", str(output_file)])

    assert result.exit_code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["version"] == "2.1.0"
    assert len(payload["runs"][0]["results"]) == 1


def test_gitlab_codequality_format_writes_to_output_file(fixture_repo, tmp_path):
    repo_root = fixture_repo("bad_phantom_target")
    output_file = tmp_path / "gl-code-quality-report.json"

    result = runner.invoke(
        app,
        [str(repo_root), "--format", "gitlab-codequality", "--output", str(output_file)],
    )

    assert result.exit_code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert len(payload) == 1


def test_table_format_writes_plain_text_to_output_file(fixture_repo, tmp_path):
    repo_root = fixture_repo("bad_phantom_target")
    output_file = tmp_path / "report.txt"

    result = runner.invoke(app, [str(repo_root), "--output", str(output_file)])

    assert result.exit_code == 1
    text = output_file.read_text(encoding="utf-8")
    assert "phantom-target" in text
    assert "\x1b[" not in text  # no ANSI codes in a file
