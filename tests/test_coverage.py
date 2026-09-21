from __future__ import annotations

from pathlib import Path

from argocd_source_lint.coverage import covered_files_for_kustomize_dir, match_directory_patterns


def _write(root: Path, relative: str, content: str = "kind: Deployment\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_resources_entry_is_covered_and_the_rest_is_not(tmp_path):
    _write(tmp_path, "kustomization.yaml", "resources:\n  - deployment.yaml\n")
    referenced = _write(tmp_path, "deployment.yaml")
    _write(tmp_path, "orphan.yaml")

    covered = covered_files_for_kustomize_dir(tmp_path)

    assert referenced.resolve() in covered
    assert (tmp_path / "orphan.yaml").resolve() not in covered
    assert (tmp_path / "kustomization.yaml").resolve() in covered  # the file itself


def test_resources_entry_pointing_at_a_directory_recurses(tmp_path):
    _write(tmp_path, "kustomization.yaml", "resources:\n  - base\n")
    _write(tmp_path, "base/kustomization.yaml", "resources:\n  - deployment.yaml\n")
    referenced = _write(tmp_path, "base/deployment.yaml")

    covered = covered_files_for_kustomize_dir(tmp_path)

    assert referenced.resolve() in covered


def test_remote_resource_reference_is_silently_skipped(tmp_path):
    _write(
        tmp_path,
        "kustomization.yaml",
        "resources:\n  - deployment.yaml\n  - https://example.invalid/other.yaml\n",
    )
    referenced = _write(tmp_path, "deployment.yaml")

    covered = covered_files_for_kustomize_dir(tmp_path)

    assert covered == {tmp_path.resolve() / "kustomization.yaml", referenced.resolve()}


def test_bases_and_components_are_covered_like_resources(tmp_path):
    _write(
        tmp_path,
        "kustomization.yaml",
        "bases:\n  - base.yaml\ncomponents:\n  - component.yaml\n",
    )
    base = _write(tmp_path, "base.yaml")
    component = _write(tmp_path, "component.yaml")

    covered = covered_files_for_kustomize_dir(tmp_path)

    assert base.resolve() in covered
    assert component.resolve() in covered


def test_patches_strategic_merge_file_entry_is_covered_inline_entry_is_not_a_path(tmp_path):
    _write(
        tmp_path,
        "kustomization.yaml",
        "patchesStrategicMerge:\n"
        "  - patch.yaml\n"
        "  - |\n"
        "    apiVersion: apps/v1\n"
        "    kind: Deployment\n",
    )
    patch = _write(tmp_path, "patch.yaml")

    covered = covered_files_for_kustomize_dir(tmp_path)

    assert patch.resolve() in covered


def test_patches_and_patches_json6902_path_are_covered(tmp_path):
    _write(
        tmp_path,
        "kustomization.yaml",
        "patches:\n"
        "  - path: patch.yaml\n"
        "    target:\n"
        "      kind: Deployment\n"
        "patchesJson6902:\n"
        "  - path: json-patch.yaml\n"
        "    target:\n"
        "      kind: Service\n",
    )
    patch = _write(tmp_path, "patch.yaml")
    json_patch = _write(tmp_path, "json-patch.yaml")

    covered = covered_files_for_kustomize_dir(tmp_path)

    assert patch.resolve() in covered
    assert json_patch.resolve() in covered


def test_configmap_and_secret_generator_files_and_envs_are_covered(tmp_path):
    _write(
        tmp_path,
        "kustomization.yaml",
        "configMapGenerator:\n"
        "  - name: app-config\n"
        "    files:\n"
        "      - config.properties\n"
        "      - key=other.properties\n"
        "    envs:\n"
        "      - config.env\n"
        "secretGenerator:\n"
        "  - name: app-secret\n"
        "    envFile: secret.env\n",
    )
    config_file = _write(tmp_path, "config.properties")
    other_file = _write(tmp_path, "other.properties")
    config_env = _write(tmp_path, "config.env")
    secret_env = _write(tmp_path, "secret.env")

    covered = covered_files_for_kustomize_dir(tmp_path)

    assert config_file.resolve() in covered
    assert other_file.resolve() in covered
    assert config_env.resolve() in covered
    assert secret_env.resolve() in covered


def test_resources_cycle_does_not_infinite_loop(tmp_path):
    _write(tmp_path, "kustomization.yaml", "resources:\n  - loop\n")
    _write(tmp_path, "loop/kustomization.yaml", "resources:\n  - ..\n")

    covered = covered_files_for_kustomize_dir(tmp_path)

    assert (tmp_path / "kustomization.yaml").resolve() in covered


def test_non_kustomize_directory_returns_empty_set(tmp_path):
    _write(tmp_path, "deployment.yaml")

    assert covered_files_for_kustomize_dir(tmp_path) == set()


def test_match_directory_patterns_is_case_sensitive():
    """ArgoCD's `directory.include`/`exclude` is matched by Go's
    `filepath.Match`, which never folds case on any platform — this must
    stay true regardless of the host OS running the linter, not silently
    over-match on Windows via `fnmatch`'s case-folding."""
    assert match_directory_patterns("deploy.yaml", "*.yaml") is True
    assert match_directory_patterns("Deploy.YAML", "*.yaml") is False


def test_match_directory_patterns_brace_alternatives_still_match():
    assert match_directory_patterns("app/deployment.yaml", "{*.yaml,app/*.yaml}") is True
