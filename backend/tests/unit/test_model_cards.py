"""Unit tests for model cards (FR-36)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.errors import NotFound
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.evaluation.base import EvalResult
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.modelcards import build_model_card, render_markdown, store_card
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry


def _registry(tmp_path: Path) -> tuple[ObjectStoreRegistry, LocalObjectStore]:
    store = LocalObjectStore(tmp_path / "store")
    return ObjectStoreRegistry(store), store


def _seed(reg: ObjectStoreRegistry) -> str:
    """Register a dataset and a model whose lineage references it; return ref."""
    reg.add_dataset(
        "patients",
        b"cohort",
        sensitivity=SensitivityLabel.PHI,
        source="ehr",
        subjects=("alice",),
    )
    lineage = LineageRecord(
        dataset_refs=("patients@1",),
        code_ref="git:abc123",
        params={"epochs": 3, "lr": 0.001, "base_model": "llama-3-8b"},
        hardware="1xA100-80GB",
        run_id="run-1",
    )
    model = reg.add_model("clf", b"weights", lineage=lineage)
    return model.ref


def test_build_card_pulls_training_data_hyperparams_hardware(tmp_path: Path) -> None:
    reg, _ = _registry(tmp_path)
    ref = _seed(reg)

    card = build_model_card(reg, ref, licence="apache-2.0")

    # Training data resolved to the dataset's sensitivity.
    assert len(card.training_data) == 1
    td = card.training_data[0]
    assert td.ref == "patients@1"
    assert td.sensitivity is SensitivityLabel.PHI
    assert td.resolved is True

    # Hyper-parameters + hardware come straight from lineage.
    assert card.hyperparams["epochs"] == 3
    assert card.hardware == "1xA100-80GB"

    # Base model derived from lineage params.
    assert card.base_model == "llama-3-8b"
    assert card.licence == "apache-2.0"


def test_build_card_includes_eval_scores_when_provided(tmp_path: Path) -> None:
    reg, _ = _registry(tmp_path)
    ref = _seed(reg)

    result = EvalResult(model_ref=ref, suite="qa-smoke", score=0.87)
    card = build_model_card(
        reg, ref, eval_result=result, known_limits=["small eval set"]
    )

    assert card.test_scores == {"qa-smoke": 0.87}
    assert card.known_limits == ("small eval set",)


def test_build_card_without_eval_has_no_scores(tmp_path: Path) -> None:
    reg, _ = _registry(tmp_path)
    ref = _seed(reg)

    card = build_model_card(reg, ref)

    assert card.test_scores == {}
    assert card.base_model == "llama-3-8b"


def test_render_markdown_contains_key_sections(tmp_path: Path) -> None:
    reg, _ = _registry(tmp_path)
    ref = _seed(reg)
    result = EvalResult(model_ref=ref, suite="qa-smoke", score=0.87)

    card = build_model_card(
        reg,
        ref,
        licence="apache-2.0",
        eval_result=result,
        known_limits=["not validated on paediatric data"],
    )
    md = render_markdown(card)

    assert "apache-2.0" in md  # licence
    assert "patients@1" in md  # training data ref
    assert "phi" in md  # sensitivity
    assert "qa-smoke" in md  # score suite
    assert "0.87" in md  # score value
    assert "not validated on paediatric data" in md  # known limit


def test_store_card_writes_markdown(tmp_path: Path) -> None:
    reg, store = _registry(tmp_path)
    ref = _seed(reg)
    card = build_model_card(reg, ref, licence="apache-2.0")

    key = store_card(store, card)

    assert key == "model_cards/clf/1.md"
    assert store.exists(key)
    assert b"apache-2.0" in store.get(key)


def test_unresolvable_training_ref_defaults_strict(tmp_path: Path) -> None:
    reg, _ = _registry(tmp_path)
    lineage = LineageRecord(dataset_refs=("ghost@9",), params={})
    model = reg.add_model("m", b"w", lineage=lineage)

    card = build_model_card(reg, model.ref)

    td = card.training_data[0]
    assert td.resolved is False
    assert td.sensitivity is SensitivityLabel.PHI  # conservative default


def test_unknown_model_raises_not_found(tmp_path: Path) -> None:
    reg, _ = _registry(tmp_path)
    with pytest.raises(NotFound):
        build_model_card(reg, "does-not-exist")
