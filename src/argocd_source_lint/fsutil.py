from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

_yaml = YAML(typ="safe")


def iter_yaml_files(directory: Path, *, recurse: bool = True) -> Iterator[Path]:
    """`.yaml`/`.yml` files under `directory`. `recurse=False` (ArgoCD's
    default for a `directory` source without an explicit `recurse: true`,
    see DESIGN.md) does not descend into subdirectories."""
    for pattern in ("*.yaml", "*.yml"):
        walker = directory.rglob(pattern) if recurse else directory.glob(pattern)
        for path in walker:
            if not path.is_file():
                continue
            if recurse and ".git" in path.parts:
                continue
            yield path


def load_yaml_documents(path: Path) -> list[dict[str, Any]]:
    """All valid YAML documents in a file (potentially multi-document). A
    file that fails to parse (e.g. a Helm template using Go syntax) simply
    returns an empty list instead of raising."""
    try:
        with path.open("r", encoding="utf-8") as f:
            docs = list(_yaml.load_all(f))
    except (YAMLError, UnicodeDecodeError):
        return []
    return [doc for doc in docs if isinstance(doc, dict)]
