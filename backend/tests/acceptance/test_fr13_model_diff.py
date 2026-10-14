"""Acceptance test: model diff between two versions (FR-13).

Story: before promoting a retrained checkpoint, an operator diffs it against the
current version. The diff shows how the quality score moved on a question set,
sample answers from each version, and a weight-change summary (how much of the
model actually changed on disk). Mock-backed and deterministic.
"""

from __future__ import annotations

from pathlib import Path

from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.evaluation.base import EvalItem
from gadziriro.evaluation.diff import model_diff
from gadziriro.evaluation.harness import reference_answer
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry


def _registry(tmp_path: Path) -> ObjectStoreRegistry:
    return ObjectStoreRegistry(LocalObjectStore(tmp_path / "store"))


def _suite() -> list[EvalItem]:
    prompts = [
        "Summarise the patient's discharge note.",
        "List the active medications.",
        "What is the follow-up date?",
        "Flag any drug interactions.",
        "What is the primary diagnosis?",
    ]
    return [EvalItem(prompt=p, expected=reference_answer(p)) for p in prompts]


def test_fr13_diff_two_versions_shows_movement_and_weight_change(
    tmp_path: Path,
) -> None:
    reg = _registry(tmp_path)
    reg.add_model(
        "clinical-notes",
        b"weights-gen-1",
        lineage=LineageRecord(dataset_refs=("notes@1",)),
    )
    reg.add_model(
        "clinical-notes",
        b"weights-gen-2-substantially-retrained",
        lineage=LineageRecord(dataset_refs=("notes@2",)),
    )

    diff = model_diff(reg, "clinical-notes@2", "clinical-notes@1", suite=_suite())

    # Score movement between the two versions.
    assert 0.0 <= diff.score_a <= 1.0
    assert 0.0 <= diff.score_b <= 1.0
    assert diff.score_delta == diff.score_a - diff.score_b

    # Sample answers from each version are exposed.
    assert diff.sample_diffs
    for sample in diff.sample_diffs:
        assert {"prompt", "answer_a", "answer_b"} <= set(sample)

    # Weight-change summary: the content changed, with a non-zero changed fraction.
    ws = diff.weight_summary
    assert ws["checksum_changed"] is True
    assert ws["checksum_a"] != ws["checksum_b"]
    assert ws["bytes_a"] > 0 and ws["bytes_b"] > 0
    assert 0.0 < ws["approx_changed_fraction"] <= 1.0


def test_fr13_diff_identical_checkpoint_reports_no_weight_change(
    tmp_path: Path,
) -> None:
    reg = _registry(tmp_path)
    # Re-registering the identical artifact (e.g. a re-upload) is not a change.
    reg.add_model("m", b"identical-bytes", lineage=LineageRecord(dataset_refs=()))
    reg.add_model("m", b"identical-bytes", lineage=LineageRecord(dataset_refs=()))

    diff = model_diff(reg, "m@1", "m@2", suite=_suite())

    # The on-disk weights are byte-identical: no weight change reported.
    assert diff.weight_summary["checksum_changed"] is False
    assert diff.weight_summary["approx_changed_fraction"] == 0.0
    assert diff.weight_summary["bytes_a"] == diff.weight_summary["bytes_b"]
    # Scores are still well-formed.
    assert 0.0 <= diff.score_a <= 1.0
    assert 0.0 <= diff.score_b <= 1.0
    assert diff.score_delta == diff.score_a - diff.score_b
