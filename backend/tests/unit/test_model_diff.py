"""Unit tests for the model diff / weight-change summary (FR-13)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.errors import NotFound
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.evaluation.base import EvalItem
from gadziriro.evaluation.diff import model_diff
from gadziriro.evaluation.harness import reference_answer
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry


def _registry(tmp_path: Path) -> ObjectStoreRegistry:
    return ObjectStoreRegistry(LocalObjectStore(tmp_path / "store"))


_PROMPTS = [f"Q{i}: what is fact {i}?" for i in range(8)]


def _suite() -> list[EvalItem]:
    return [EvalItem(prompt=p, expected=reference_answer(p)) for p in _PROMPTS]


def test_diff_of_different_versions_reports_checksum_change(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.add_model("m", b"weights-one", lineage=LineageRecord(dataset_refs=()))
    reg.add_model("m", b"weights-two-different", lineage=LineageRecord(dataset_refs=()))

    result = model_diff(reg, "m@1", "m@2")

    ws = result.weight_summary
    assert ws["checksum_changed"] is True
    assert ws["bytes_a"] != ws["bytes_b"]
    assert 0.0 < ws["approx_changed_fraction"] <= 1.0
    assert isinstance(ws["bytes_a"], int) and isinstance(ws["bytes_b"], int)


def test_diff_of_identical_content_reports_no_change(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.add_model("m", b"same-weights", lineage=LineageRecord(dataset_refs=()))
    reg.add_model("m", b"same-weights", lineage=LineageRecord(dataset_refs=()))

    result = model_diff(reg, "m@1", "m@2")

    ws = result.weight_summary
    assert ws["checksum_changed"] is False
    assert ws["approx_changed_fraction"] == 0.0
    assert ws["bytes_a"] == ws["bytes_b"]


def test_diff_without_suite_only_fills_weight_summary(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.add_model("m", b"one", lineage=LineageRecord(dataset_refs=()))
    reg.add_model("m", b"two", lineage=LineageRecord(dataset_refs=()))

    result = model_diff(reg, "m@1", "m@2", suite=None)

    assert result.score_a == 0.0
    assert result.score_b == 0.0
    assert result.score_delta == 0.0
    assert result.sample_diffs == ()
    assert result.weight_summary["checksum_changed"] is True


def test_diff_with_suite_fills_scores_and_summary(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.add_model("m", b"one", lineage=LineageRecord(dataset_refs=()))
    reg.add_model("m", b"two-different", lineage=LineageRecord(dataset_refs=()))

    result = model_diff(reg, "m@2", "m@1", suite=_suite())

    assert 0.0 <= result.score_a <= 1.0
    assert 0.0 <= result.score_b <= 1.0
    assert result.score_delta == pytest.approx(result.score_a - result.score_b)
    assert result.sample_diffs
    assert result.weight_summary["checksum_changed"] is True


def test_diff_unknown_model_raises_not_found(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.add_model("m", b"one", lineage=LineageRecord(dataset_refs=()))
    with pytest.raises(NotFound):
        model_diff(reg, "m@1", "ghost@1")
