from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def tool_version() -> str:
    try:
        return version("argocd-source-lint")
    except PackageNotFoundError:
        return "0.0.0-dev"
