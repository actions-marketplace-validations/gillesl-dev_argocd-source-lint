from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    UNVERIFIABLE = "unverifiable"


class IgnoreDiffRule(BaseModel):
    group: str | None = None
    kind: str
    name: str | None = None
    namespace: str | None = None
    json_pointers: list[str] = Field(default_factory=list)
    jq_path_expressions: list[str] = Field(default_factory=list)
    managed_fields_managers: list[str] = Field(default_factory=list)


class Source(BaseModel):
    repo_url: str
    target_revision: str
    path: str | None = None
    chart: str | None = None
    ref: str | None = None
    helm_value_files: list[str] = Field(default_factory=list)
    # Line of each `helm_value_files` entry, same order/index — best-effort
    # (None when the source YAML wasn't round-trip parsed, e.g. in tests
    # that build a `Source` directly).
    helm_value_files_lines: list[int | None] = Field(default_factory=list)
    # `spec.source(s)[].directory` (only relevant when `path` is a directory
    # of raw manifests, not a Helm chart or a Kustomize overlay).
    # Defaults aligned with ArgoCD: recurse=false, no filter.
    directory_recurse: bool = False
    directory_include: str | None = None
    directory_exclude: str | None = None
    # 1-indexed line where this source's YAML mapping starts, for
    # `Finding.line` — best-effort, None when unavailable.
    line: int | None = None


class ExpectedIgnoreDiff(BaseModel):
    kind: str
    name_pattern: str


class KnownOperatorSignature(BaseModel):
    """A signature from the `rules/known-operators.yaml` pack (used by the
    missing-ignore-diff rule): a trigger CRD, how to extract the instance
    name from it, and the expected derived resources with
    `ignoreDifferences`."""

    crd_trigger: str
    name_from: str
    expect_ignore_on: list[ExpectedIgnoreDiff]


class Application(BaseModel):
    name: str
    namespace: str
    sources: list[Source]
    sync_policy_self_heal: bool = False
    # Line of the `selfHeal` key, when true — for `missing-ignore-diff`'s
    # `Finding.line` (best-effort, None when unavailable).
    self_heal_line: int | None = None
    ignore_differences: list[IgnoreDiffRule] = Field(default_factory=list)
    source_file: Path
    # `spec.project` (defaults to "default", same as ArgoCD itself) and
    # `spec.destination` — used by `project-scope-violation` only.
    project: str = "default"
    project_line: int | None = None
    destination_server: str | None = None
    destination_name: str | None = None
    destination_namespace: str | None = None


class AppProjectDestination(BaseModel):
    server: str | None = None
    name: str | None = None
    namespace: str | None = None


class AppProject(BaseModel):
    """`kind: AppProject` — used only by `project-scope-violation` to
    check an Application's sources/destination against the scope its own
    `spec.project` grants it."""

    name: str
    source_repos: list[str] = Field(default_factory=list)
    destinations: list[AppProjectDestination] = Field(default_factory=list)
    source_file: Path


class Finding(BaseModel):
    rule_id: str
    severity: Severity
    application: str
    message: str
    file: Path
    line: int | None = None
