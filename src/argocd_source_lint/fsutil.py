from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

# Round-trip (not "safe") mode: it's the only one that keeps line/column
# info (`.lc`) on the parsed `CommentedMap`/`CommentedSeq`, needed by
# `loader.py` to populate `Finding.line`. Still behaves as a plain
# dict/list for every existing `.get()`/iteration call site.
_yaml = YAML(typ="rt")

# A YAML anchor referenced twice by a later anchor, N layers deep,
# expands to 2^N nodes if anything ever fully materializes it (e.g. a
# naive `str()` on the parsed value) -- while staying a few hundred
# bytes on disk ("billion laughs"). ruamel's loader itself is safe (an
# alias resolves to the *same* object, not a copy -- confirmed
# empirically, not assumed), so parsing never hangs; the risk is
# entirely downstream, the moment something stringifies/walks the
# result without knowing it may be densely aliased. Rejecting a
# document whose *fully expanded* size would be unreasonable -- computed
# via memoized recursion (`is_within_budget`), so this check itself
# costs one pass over the *distinct* nodes, never the exploded count --
# closes that off at the one place virtually everything here reads YAML
# through, rather than defensively re-checking every later call site
# that stringifies a value (see DESIGN.md "YAML alias bombs").
_MAX_EXPANDED_NODES = 1_000_000


def is_within_budget(node: Any, memo: dict[int, int] | None = None) -> bool:
    """`False` if `node`, fully expanded, would exceed `_MAX_EXPANDED_NODES`
    nodes -- generous headroom for any real manifest, far below what an
    alias bomb reaches within a handful of anchor layers. `memo` (keyed by
    `id()`) makes this one pass over the distinct nodes: an aliased
    subtree's size is computed once and reused for every later reference
    to it, exactly the reuse that makes the bomb small on disk in the
    first place."""
    memo = {} if memo is None else memo
    return _expanded_size(node, memo, _MAX_EXPANDED_NODES) is not None


_VISITING = -1  # sentinel: a genuine cycle isn't constructible through a
# YAML anchor (an alias can only reference an anchor already fully
# resolved -- confirmed empirically, a forward self-reference resolves
# to `None` instead), but this guards against one anyway rather than
# trusting that to hold across every YAML feature and library version.


def _expanded_size(node: Any, memo: dict[int, int], budget: int) -> int | None:
    if not isinstance(node, (dict, list)):
        return 1

    node_id = id(node)
    if node_id in memo:
        return None if memo[node_id] == _VISITING else memo[node_id]

    memo[node_id] = _VISITING
    total = 1
    for child in node.values() if isinstance(node, dict) else node:
        child_size = _expanded_size(child, memo, budget)
        if child_size is None:
            return None
        total += child_size
        if total > budget:
            return None

    memo[node_id] = total
    return total


def walk_tree(directory: Path) -> Iterator[Path]:
    """Every file and directory under `directory`, breaking a directory
    symlink/junction cycle instead of following it forever -- confirmed
    to hang otherwise (a junction pointing back at an ancestor, a few
    KB on disk); neither `Path.rglob` nor even `os.walk(followlinks=
    False)` protect against it, only a "real" symlink, and a Windows
    junction isn't one (`Path.is_symlink()` is `False` for it too --
    see DESIGN.md "A directory symlink/junction cycle"). `.git` is
    never descended into. Shared by `iter_yaml_files` and the
    ApplicationSet `git` generator's own directory/file discovery."""
    yield from _walk(directory, set())


def _walk(directory: Path, seen: set[Path]) -> Iterator[Path]:
    try:
        resolved = directory.resolve()
    except OSError:
        return
    if resolved in seen:
        return
    seen.add(resolved)

    try:
        entries = list(directory.iterdir())
    except OSError:
        return

    for entry in entries:
        if entry.name == ".git":
            continue
        yield entry
        if entry.is_dir():
            yield from _walk(entry, seen)


def iter_yaml_files(directory: Path, *, recurse: bool = True) -> Iterator[Path]:
    """`.yaml`/`.yml` files under `directory`. `recurse=False` (ArgoCD's
    default for a `directory` source without an explicit `recurse: true`,
    see DESIGN.md) does not descend into subdirectories."""
    if not recurse:
        for pattern in ("*.yaml", "*.yml"):
            for path in directory.glob(pattern):
                if path.is_file():
                    yield path
        return

    for path in walk_tree(directory):
        if path.is_file() and path.name.endswith((".yaml", ".yml")):
            yield path


def load_yaml_documents(path: Path) -> list[dict[str, Any]]:
    """All valid YAML documents in a file (potentially multi-document). A
    file that fails to parse (e.g. a Helm template using Go syntax), or
    a YAML alias bomb that would blow past `is_within_budget`, simply
    returns an empty list instead of raising or hanging."""
    try:
        with path.open("r", encoding="utf-8") as f:
            docs = list(_yaml.load_all(f))
    except (YAMLError, UnicodeDecodeError):
        return []
    return [doc for doc in docs if isinstance(doc, dict) and is_within_budget(doc)]
