"""Unit tests for the mock fine-tune engine and templates (FR-10, FR-09)."""

from __future__ import annotations

from pathlib import Path

from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.modelstudio.base import FineTuneMethod, TrainingSpec
from gadziriro.modelstudio.finetune import (
    DEFAULT_METHOD,
    full_template,
    lora_template,
    qlora_template,
    run_finetune,
    spec_from_form,
)
from gadziriro.registry.store import ObjectStoreRegistry
from gadziriro.tracking.store import ObjectStoreTracker


def _env(tmp_path: Path) -> tuple[ObjectStoreRegistry, ObjectStoreTracker]:
    reg = ObjectStoreRegistry(LocalObjectStore(tmp_path / "registry"))
    tracker = ObjectStoreTracker(LocalObjectStore(tmp_path / "runs"))
    return reg, tracker


def _seed_dataset(reg: ObjectStoreRegistry) -> str:
    dv = reg.add_dataset(
        "patients",
        b"cohort",
        sensitivity=SensitivityLabel.PHI,
        source="ehr",
        subjects=("alice",),
    )
    return dv.ref


def _spec(dataset_ref: str, **over) -> TrainingSpec:
    base = dict(
        base_model="llama-3-8b",
        method=FineTuneMethod.QLORA,
        dataset_refs=(dataset_ref,),
        output_name="clf",
        hyperparams=qlora_template(),
        code_ref="git:abc123",
    )
    base.update(over)
    return TrainingSpec(**base)


def test_qlora_is_the_default_method() -> None:
    assert DEFAULT_METHOD is FineTuneMethod.QLORA


def test_templates_expose_method_and_sane_defaults() -> None:
    assert lora_template()["method"] == FineTuneMethod.LORA.value
    assert qlora_template()["method"] == FineTuneMethod.QLORA.value
    assert full_template()["method"] == FineTuneMethod.FULL.value
    # QLoRA carries the quantization knobs that make it fit one GPU.
    assert qlora_template()["quantization"] == "nf4"
    assert full_template()["epochs"] >= 1


def test_run_finetune_registers_model_with_linking_lineage(tmp_path: Path) -> None:
    reg, tracker = _env(tmp_path)
    ref = _seed_dataset(reg)

    result = run_finetune(reg, tracker, _spec(ref))

    mv = reg.get_model("clf")
    assert result.model_ref == mv.ref == "clf@1"
    # Lineage links the exact dataset refs and the run that produced it (FR-07).
    assert mv.lineage.dataset_refs == (ref,)
    assert mv.lineage.run_id == result.run_id
    assert mv.lineage.code_ref == "git:abc123"
    assert mv.lineage.params == qlora_template()
    # DSAR query path works through the new model's lineage.
    assert [m.ref for m in reg.models_for_subject("alice")] == [mv.ref]


def test_same_spec_reproduces_same_checksum(tmp_path: Path) -> None:
    reg, tracker = _env(tmp_path)
    ref = _seed_dataset(reg)

    r1 = run_finetune(reg, tracker, _spec(ref))
    r2 = run_finetune(reg, tracker, _spec(ref))

    # Two versions were registered, with distinct runs ...
    assert r1.run_id != r2.run_id
    versions = reg.list_model_versions("clf")
    assert [v.version for v in versions] == [1, 2]
    # ... but the deterministic artifact yields an identical checksum (FR-09).
    assert versions[0].checksum == versions[1].checksum


def test_different_spec_changes_checksum(tmp_path: Path) -> None:
    reg, tracker = _env(tmp_path)
    ref = _seed_dataset(reg)

    run_finetune(reg, tracker, _spec(ref))
    changed = _spec(ref, base_model="mistral-7b")
    run_finetune(reg, tracker, changed)

    versions = reg.list_model_versions("clf")
    assert versions[0].checksum != versions[1].checksum


def test_tracker_run_exists_and_is_finished(tmp_path: Path) -> None:
    reg, tracker = _env(tmp_path)
    ref = _seed_dataset(reg)

    result = run_finetune(reg, tracker, _spec(ref))

    run = tracker.get_run(result.run_id)
    assert run.status == "finished"
    assert run.ended_at is not None
    assert run.dataset_refs == (ref,)
    assert run.params == qlora_template()
    # A mock metric was logged and echoed on the result.
    assert "train_loss" in run.metrics
    assert run.metrics["train_loss"] == result.metrics["train_loss"]


def test_form_and_code_specs_produce_equivalent_results(tmp_path: Path) -> None:
    reg, tracker = _env(tmp_path)
    ref = _seed_dataset(reg)

    # Analyst (form) path.
    form = {
        "base_model": "llama-3-8b",
        "dataset_refs": [ref],
        "output_name": "clf",
        "code_ref": "git:abc123",
        # method omitted -> defaults to QLoRA.
    }
    form_spec = spec_from_form(form)
    assert form_spec.method is FineTuneMethod.QLORA
    assert form_spec.hyperparams == qlora_template()

    # Engineer (code) path, same inputs.
    code_spec = _spec(ref)

    form_result = run_finetune(reg, tracker, form_spec)
    code_result = run_finetune(reg, tracker, code_spec)

    # Same engine => identical artifact checksum and identical metrics.
    versions = {v.version: v for v in reg.list_model_versions("clf")}
    assert versions[1].checksum == versions[2].checksum
    assert form_result.metrics == code_result.metrics


def test_spec_from_form_merges_hyperparam_overrides() -> None:
    form = {
        "base_model": "llama-3-8b",
        "dataset_refs": ["patients@1"],
        "output_name": "clf",
        "method": "lora",
        "hyperparams": {"epochs": 10},
    }
    spec = spec_from_form(form)
    assert spec.method is FineTuneMethod.LORA
    assert spec.hyperparams["epochs"] == 10  # override applied
    assert spec.hyperparams["lora_r"] == lora_template()["lora_r"]  # template kept
