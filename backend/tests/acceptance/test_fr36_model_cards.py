"""Acceptance test: model cards (FR-36).

Every model can produce a card stating its licence, training data (with
sensitivity), test scores, and known limitations — the fact sheet a reviewer
needs before trusting a model.
"""

from __future__ import annotations

from pathlib import Path

from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.evaluation.base import EvalResult
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.modelcards import build_model_card, render_markdown, store_card
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry


def test_fr36_every_model_gets_a_complete_card(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "store")
    reg = ObjectStoreRegistry(store)

    # Register training data and a model built from it.
    reg.add_dataset(
        "clinical-notes",
        b"notes",
        sensitivity=SensitivityLabel.PHI,
        source="emr",
        subjects=("alice", "bob"),
    )
    reg.add_dataset(
        "public-corpus",
        b"corpus",
        sensitivity=SensitivityLabel.PUBLIC,
        source="wiki",
    )
    lineage = LineageRecord(
        dataset_refs=("clinical-notes@1", "public-corpus@1"),
        code_ref="git:deadbeef",
        params={"epochs": 5, "lr": 0.0003, "base_model": "mistral-7b"},
        hardware="2xA100-80GB",
        run_id="run-42",
    )
    model = reg.add_model("triage", b"weights", lineage=lineage)

    # Evaluation supplies measured scores.
    eval_result = EvalResult(model_ref=model.ref, suite="triage-eval", score=0.91)

    # Every model can get a card.
    card = build_model_card(
        reg,
        model.ref,
        licence="apache-2.0",
        eval_result=eval_result,
        known_limits=[
            "English-only clinical notes",
            "not validated for emergency triage",
        ],
    )

    # Licence.
    assert card.licence == "apache-2.0"
    # Training data with sensitivity.
    refs = {td.ref: td.sensitivity for td in card.training_data}
    assert refs == {
        "clinical-notes@1": SensitivityLabel.PHI,
        "public-corpus@1": SensitivityLabel.PUBLIC,
    }
    # Test scores.
    assert card.test_scores == {"triage-eval": 0.91}
    # Known limitations.
    assert len(card.known_limits) == 2
    # Base model + hardware + hyperparams captured.
    assert card.base_model == "mistral-7b"
    assert card.hardware == "2xA100-80GB"
    assert card.hyperparams["epochs"] == 5

    # The rendered fact sheet is readable and self-contained, and persists.
    md = render_markdown(card)
    for needle in (
        "apache-2.0",
        "clinical-notes@1",
        "phi",
        "triage-eval",
        "0.91",
        "English-only clinical notes",
    ):
        assert needle in md

    key = store_card(store, card)
    assert store.exists(key)
    assert store.get(key).decode("utf-8") == md
