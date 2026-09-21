from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from argocd_source_lint.fsutil import is_within_budget, load_yaml_documents


def _alias_bomb_yaml(layers: int, tail: str) -> str:
    """A YAML "billion laughs" document: each layer aliases the previous
    one twice, so `layers` anchors (a tiny file) expand to 2**layers
    nodes if anything ever fully materializes it."""
    lines = ['a0: &a0 ["x"]']
    for i in range(1, layers):
        lines.append(f"a{i}: &a{i} [*a{i - 1}, *a{i - 1}]")
    lines.append(tail.format(ref=f"a{layers - 1}"))
    return "\n".join(lines) + "\n"


def test_is_within_budget_true_for_an_ordinary_document():
    doc = {"kind": "Application", "spec": {"source": {"path": "manifests/app"}}}

    assert is_within_budget(doc) is True


def test_is_within_budget_false_for_an_alias_bomb():
    text = _alias_bomb_yaml(30, "bomb: *{ref}")
    doc = YAML(typ="rt").load(text)

    assert is_within_budget(doc) is False


def test_is_within_budget_reuses_a_shared_subtree_across_siblings():
    """The whole point: an alias referenced twice must be *sized* once,
    not twice -- otherwise this check would be exponential itself."""
    doc = YAML(typ="rt").load('a: &x ["1", "2", "3"]\nb: [*x, *x, *x, *x, *x]\n')

    assert is_within_budget(doc) is True


def test_load_yaml_documents_silently_drops_an_alias_bomb(tmp_path: Path):
    """Same fallback as a file that fails to parse outright -- never
    hangs, never raises."""
    path = tmp_path / "bomb.yaml"
    path.write_text(
        _alias_bomb_yaml(
            30,
            "apiVersion: *{ref}\nkind: Application\nmetadata:\n  name: bomb\n",
        ),
        encoding="utf-8",
    )

    assert load_yaml_documents(path) == []


def test_load_yaml_documents_still_parses_an_ordinary_multi_document_file(tmp_path: Path):
    path = tmp_path / "docs.yaml"
    path.write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: a\n---\n"
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: b\n",
        encoding="utf-8",
    )

    docs = load_yaml_documents(path)

    assert [doc["metadata"]["name"] for doc in docs] == ["a", "b"]
