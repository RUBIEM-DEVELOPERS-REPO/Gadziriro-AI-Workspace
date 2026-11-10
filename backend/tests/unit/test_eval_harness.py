"""Unit tests for the evaluation harness (FR-11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.errors import NotFound
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.evaluation.base import EvalItem
from gadziriro.evaluation.harness import (
    compare,
    default_answer_fn,
    evaluate,
    reference_answer,
)
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry


def _registry(tmp_path: Path) -> ObjectStoreRegistry:
    return ObjectStoreRegistry(LocalObjectStore(tmp_path / "store"))


def _two_versions(reg: ObjectStoreRegistry) -> None:
    """Register model ``m`` twice with different bytes (-> m@1, m@2)."""
    reg.add_model("m", b"weights-one", lineage=LineageRecord(dataset_refs=()))
    reg.add_model("m", b"weights-two-different", lineage=LineageRecord(dataset_refs=()))


_PROMPTS = [f"Q{i}: what is fact {i}?" for i in range(8)]


def _ground_truth_suite() -> list[EvalItem]:
    """A suite whose expected answers are the canonical reference answers."""
    return [EvalItem(prompt=p, expected=reference_answer(p)) for p in _PROMPTS]


def test_evaluate_returns_score_in_unit_interval_with_detail(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _two_versions(reg)

    result = evaluate(reg, "m@1", _ground_truth_suite(), suite_name="facts")

    assert result.suite == "facts"
    assert 0.0 <= result.score <= 1.0
    assert len(result.per_item) == len(_PROMPTS)
    assert result.samples  # a few captured
    assert all({"prompt", "answer"} <= set(s) for s in result.samples)
    assert all(
        {"prompt", "expected", "answer", "correct", "weight", "score"} <= set(d)
        for d in result.per_item
    )


def test_correct_suite_scores_higher_than_wrong_suite(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _two_versions(reg)

    # A suite whose expected answers are exactly what the model outputs.
    correct = [
        EvalItem(prompt=p, expected=default_answer_fn("m@1", p)) for p in _PROMPTS
    ]
    # A suite the model can never get right.
    wrong = [EvalItem(prompt=p, expected="definitely-not-the-answer") for p in _PROMPTS]

    good = evaluate(reg, "m@1", correct)
    bad = evaluate(reg, "m@1", wrong)

    assert good.score == 1.0
    assert bad.score == 0.0
    assert good.score > bad.score


def test_different_versions_can_score_differently(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _two_versions(reg)
    suite = _ground_truth_suite()

    s1 = evaluate(reg, "m@1", suite).score
    s2 = evaluate(reg, "m@2", suite).score

    assert s1 != s2


def test_unknown_model_ref_raises_not_found(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    with pytest.raises(NotFound):
        evaluate(reg, "ghost", _ground_truth_suite())
    reg.add_model("m", b"w", lineage=LineageRecord(dataset_refs=()))
    with pytest.raises(NotFound):
        evaluate(reg, "m@99", _ground_truth_suite())


def test_answer_fn_injection_overrides_answers(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _two_versions(reg)
    suite = [EvalItem(prompt=p, expected="FIXED") for p in _PROMPTS]

    result = evaluate(reg, "m@1", suite, answer_fn=lambda ref, prompt: "FIXED")

    assert result.score == 1.0
    assert all(d["answer"] == "FIXED" for d in result.per_item)


def test_compare_runs_both_versions_on_same_suite(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _two_versions(reg)
    suite = _ground_truth_suite()

    cmp = compare(reg, "m@2", "m@1", suite)

    assert cmp.a_ref == "m@2"
    assert cmp.b_ref == "m@1"
    assert cmp.score_delta == pytest.approx(cmp.score_a - cmp.score_b)
    assert cmp.score_a != cmp.score_b  # versions move the score
    assert cmp.sample_diffs
    assert all({"prompt", "answer_a", "answer_b"} <= set(d) for d in cmp.sample_diffs)
