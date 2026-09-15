from __future__ import annotations

from importlib.metadata import PackageNotFoundError

import argocd_source_lint


def test_tool_version_returns_installed_version():
    assert argocd_source_lint.tool_version() != ""


def test_tool_version_falls_back_when_not_installed(monkeypatch):
    def _raise(_name: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(argocd_source_lint, "version", _raise)

    assert argocd_source_lint.tool_version() == "0.0.0-dev"
