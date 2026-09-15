from __future__ import annotations

import json

from typer.testing import CliRunner

from argocd_source_lint.cli import app

runner = CliRunner()


def test_version_flag_prints_version_and_exits_0():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip()


def test_exit_code_1_on_phantom_target_error(fixture_repo):
    repo_root = fixture_repo("bad_phantom_target")

    result = runner.invoke(app, [str(repo_root)])

    assert result.exit_code == 1


def test_exit_code_0_on_good_repo(fixture_repo):
    repo_root = fixture_repo("good_repo")

    result = runner.invoke(app, [str(repo_root)])

    assert result.exit_code == 0


def test_write_baseline_accepts_current_findings_and_exits_0(fixture_repo):
    repo_root = fixture_repo("bad_phantom_target")

    result = runner.invoke(app, [str(repo_root), "--write-baseline"])

    assert result.exit_code == 0
    assert (repo_root / ".argocd-lint-baseline.yaml").is_file()


def test_baselined_finding_no_longer_blocks_ci(fixture_repo):
    repo_root = fixture_repo("bad_phantom_target")
    runner.invoke(app, [str(repo_root), "--write-baseline"])

    result = runner.invoke(app, [str(repo_root)])

    assert result.exit_code == 0
    assert "phantom-target" not in result.stdout


def test_new_finding_still_blocks_ci_after_baselining_a_different_one(fixture_repo):
    repo_root = fixture_repo("bad_phantom_target")
    runner.invoke(app, [str(repo_root), "--write-baseline"])
    # A new, never-baselined finding appears (a fresh orphan file).
    orphan = repo_root / "manifests" / "new-orphan.yaml"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: new-orphan\n")
    (repo_root / ".argocd-lint.yaml").write_text("scan_roots:\n  - manifests/\n")

    result = runner.invoke(app, [str(repo_root)])

    assert result.exit_code == 1
    assert "phantom-target" not in result.stdout
    assert "orphan-source" in result.stdout


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
