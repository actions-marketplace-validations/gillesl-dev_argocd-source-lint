from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from argocd_source_lint.models import KnownOperatorSignature, Severity

DEFAULT_RULE_SEVERITIES: dict[str, Severity] = {
    "orphan-source": Severity.ERROR,
    "broken-values-ref": Severity.ERROR,
    "missing-ignore-diff": Severity.WARNING,
    "phantom-target": Severity.ERROR,
    "unresolvable-generator": Severity.INFO,
    "double-coverage": Severity.ERROR,
    "revision-mismatch": Severity.INFO,
    "project-scope-violation": Severity.ERROR,
    "hpa-selfheal-conflict": Severity.WARNING,
    "sync-validation-disabled": Severity.INFO,
    "duplicate-application-name": Severity.ERROR,
    "malformed-ignore-diff-pointer": Severity.WARNING,
    "unknown-sync-option": Severity.WARNING,
}


class Policy(BaseModel):
    scan_roots: list[str] = Field(default_factory=list)
    rules: dict[str, Severity] = Field(default_factory=lambda: dict(DEFAULT_RULE_SEVERITIES))
    unverifiable_blocks_ci: bool = True
    exclude_paths: list[str] = Field(default_factory=list)
    # Signatures added on top of the built-in community pack
    # (`rules/known-operators.yaml`, used by missing-ignore-diff) — never a
    # replacement, always a complement for internal operators.
    known_operators: list[KnownOperatorSignature] = Field(default_factory=list)


def load_policy(repo_root: Path, filename: str = ".argocd-lint.yaml") -> Policy:
    """Loads `.argocd-lint.yaml` from the repo root and merges it with the
    defaults: `rules` merges key by key, other fields are replaced
    outright when present in the file."""
    policy_file = repo_root / filename
    if not policy_file.exists():
        return Policy()

    yaml = YAML(typ="safe")
    with policy_file.open("r", encoding="utf-8") as f:
        raw = yaml.load(f) or {}

    merged = Policy().model_dump()
    for key in ("scan_roots", "unverifiable_blocks_ci", "exclude_paths", "known_operators"):
        if key in raw:
            merged[key] = raw[key]
    if "rules" in raw:
        merged["rules"] = {**merged["rules"], **raw["rules"]}

    return Policy.model_validate(merged)
