from __future__ import annotations

from pathlib import Path

from argocd_source_lint.baseline import (
    DEFAULT_BASELINE_FILENAME,
    load_baseline,
    split_by_baseline,
    write_baseline,
)
from argocd_source_lint.models import Finding, Severity

_ACCEPTED = Finding(
    rule_id="orphan-source",
    severity=Severity.ERROR,
    application="",
    message="File not covered by any Application source: legacy/dead.yaml",
    file=Path("legacy/dead.yaml"),
)

_NEW = Finding(
    rule_id="phantom-target",
    severity=Severity.ERROR,
    application="demo-app",
    message="path not found",
    file=Path("bootstrap/argocd-apps/demo-app.yaml"),
)


def test_load_baseline_returns_empty_set_when_file_missing(tmp_path):
    assert load_baseline(tmp_path) == set()


def test_write_then_load_round_trips(tmp_path):
    write_baseline(tmp_path, [_ACCEPTED])

    baseline_file = tmp_path / DEFAULT_BASELINE_FILENAME
    assert baseline_file.is_file()

    baseline = load_baseline(tmp_path)
    new, known = split_by_baseline([_ACCEPTED, _NEW], baseline)

    assert known == [_ACCEPTED]
    assert new == [_NEW]


def test_split_by_baseline_treats_everything_as_new_without_a_baseline_file(tmp_path):
    new, known = split_by_baseline([_ACCEPTED, _NEW], load_baseline(tmp_path))

    assert new == [_ACCEPTED, _NEW]
    assert known == []


def test_write_baseline_overwrites_previous_content(tmp_path):
    write_baseline(tmp_path, [_ACCEPTED, _NEW])
    write_baseline(tmp_path, [_NEW])

    baseline = load_baseline(tmp_path)
    new, known = split_by_baseline([_ACCEPTED, _NEW], baseline)

    assert new == [_ACCEPTED]
    assert known == [_NEW]
