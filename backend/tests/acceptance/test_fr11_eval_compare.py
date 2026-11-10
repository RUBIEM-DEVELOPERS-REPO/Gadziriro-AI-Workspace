"""Acceptance test: evaluation harness + version compare (FR-11).

Story: a team keeps a held-out customer question set, evaluates a model version
against it to get a quality score, and compares two versions side by side to see
which answers moved and by how much. Everything is mock-backed and
deterministic (no real inference): a version "answers" via the harness's default
deterministic answerer, whose competence rises with the version number.
"""

from __future__ import annotations

from pathlib import Path

from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.evaluation.base import EvalItem
from gadziriro.evaluation.harness import compare, evaluate, reference_answer
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry


def _registry(tmp_path: Path) -> ObjectStoreRegistry:
    return ObjectStoreRegistry(LocalObjectStore(tmp_path / "store"))


def _customer_question_set() -> list[EvalItem]:
    """A weighted held-out question set; ground truth = canonical answers."""
    questions = [
        "How do I reset my account password?",
        "What are your support hours?",
        "Can I export my data?",
        "Does the plan include offline mode?",
        "How is my data encrypted at rest?",
        "What is the refund window?",
    ]
    # Safety-critical questions weigh more than routine ones.
    weights = [2.0, 1.0, 1.0, 1.0, 2.0, 1.0]
    return [
        EvalItem(prompt=q, expected=reference_answer(q), weight=w)
        for q, w in zip(questions, weights, strict=True)
    ]


def test_fr11_evaluate_and_compare_two_versions(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    # Two fine-tuned versions of the support assistant with different weights.
    reg.add_model(
        "support-assistant",
        b"checkpoint-v1-bytes",
        lineage=LineageRecord(dataset_refs=("faq@1",), code_ref="c1"),
    )
    reg.add_model(
        "support-assistant",
        b"checkpoint-v2-bytes-retrained",
        lineage=LineageRecord(dataset_refs=("faq@2",), code_ref="c2"),
    )

    suite = _customer_question_set()

    # FR-11: evaluate a single version against the customer question set.
    v2 = evaluate(reg, "support-assistant@2", suite, suite_name="customer-faq")
    assert v2.suite == "customer-faq"
    assert 0.0 <= v2.score <= 1.0
    assert len(v2.per_item) == len(suite)
    assert v2.samples

    # FR-11: compare the two versions side by side on the SAME suite.
    cmp = compare(reg, "support-assistant@2", "support-assistant@1", suite)

    assert cmp.a_ref == "support-assistant@2"
    assert cmp.b_ref == "support-assistant@1"
    assert 0.0 <= cmp.score_a <= 1.0
    assert 0.0 <= cmp.score_b <= 1.0
    # The newer version scores at least as well, and the score moved.
    assert cmp.score_a >= cmp.score_b
    assert cmp.score_a != cmp.score_b
    assert cmp.score_delta == cmp.score_a - cmp.score_b

    # sample_diffs expose per-prompt answers from both versions.
    assert cmp.sample_diffs
    for diff in cmp.sample_diffs:
        assert {"prompt", "answer_a", "answer_b"} <= set(diff)
