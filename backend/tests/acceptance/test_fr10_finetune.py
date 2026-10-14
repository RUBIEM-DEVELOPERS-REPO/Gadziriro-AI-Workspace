"""Acceptance tests for FR-10: fine-tune templates + (mock) training engine.

The requirement: an analyst (no-code form) and an engineer (code) launch the
*same* fine-tune engine; each supported method (LoRA / QLoRA / full, QLoRA the
default) produces a registered, lineage-tracked, reproducible model (FR-07,
FR-09). Real GPU training is a target-hardware concern (stub at the bottom).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.modelstudio.base import FineTuneMethod, TrainingSpec
from gadziriro.modelstudio.finetune import run_finetune, spec_from_form, template_for
from gadziriro.registry.store import ObjectStoreRegistry
from gadziriro.tracking.store import ObjectStoreTracker

_ON_TARGET = sys.platform.startswith("linux") and shutil.which("nvidia-smi") is not None


def _env(tmp_path: Path) -> tuple[ObjectStoreRegistry, ObjectStoreTracker]:
    reg = ObjectStoreRegistry(LocalObjectStore(tmp_path / "registry"))
    tracker = ObjectStoreTracker(LocalObjectStore(tmp_path / "runs"))
    reg.add_dataset(
        "patients",
        b"cohort",
        sensitivity=SensitivityLabel.PHI,
        source="ehr",
        subjects=("alice",),
    )
    return reg, tracker


@pytest.mark.parametrize("method", list(FineTuneMethod))
def test_fr10_each_method_produces_tracked_lineage_model(
    tmp_path: Path, method: FineTuneMethod
) -> None:
    reg, tracker = _env(tmp_path)
    spec = TrainingSpec(
        base_model="llama-3-8b",
        method=method,
        dataset_refs=("patients@1",),
        output_name=f"clf-{method.value}",
        hyperparams=template_for(method),
        code_ref="git:abc123",
    )

    result = run_finetune(reg, tracker, spec)

    # Registered model with lineage tracing the dataset + run (FR-07/FR-09).
    mv = reg.get_model(spec.output_name)
    assert result.model_ref == mv.ref
    assert mv.lineage.dataset_refs == ("patients@1",)
    assert mv.lineage.run_id == result.run_id
    assert result.method is method

    # The run is a finished, reproducible record.
    run = tracker.get_run(result.run_id)
    assert run.status == "finished"
    assert run.params == template_for(method)
    assert run.metrics["train_loss"] == result.metrics["train_loss"]

    # DSAR lineage query reaches the new model.
    assert mv.ref in [m.ref for m in reg.models_for_subject("alice")]


def test_fr10_qlora_is_the_default_for_the_analyst_form(tmp_path: Path) -> None:
    reg, tracker = _env(tmp_path)
    # Analyst submits a form without naming a method.
    form = {
        "base_model": "llama-3-8b",
        "dataset_refs": ["patients@1"],
        "output_name": "clf",
    }
    spec = spec_from_form(form)
    assert spec.method is FineTuneMethod.QLORA

    result = run_finetune(reg, tracker, spec)
    assert result.method is FineTuneMethod.QLORA
    assert reg.get_model("clf").ref == result.model_ref


def test_fr10_same_spec_is_reproducible(tmp_path: Path) -> None:
    reg, tracker = _env(tmp_path)
    spec = TrainingSpec(
        base_model="llama-3-8b",
        method=FineTuneMethod.QLORA,
        dataset_refs=("patients@1",),
        output_name="clf",
        hyperparams=template_for(FineTuneMethod.QLORA),
    )
    run_finetune(reg, tracker, spec)
    run_finetune(reg, tracker, spec)

    v1, v2 = reg.list_model_versions("clf")
    assert v1.checksum == v2.checksum  # FR-09 reproducibility


@pytest.mark.target_hardware
@pytest.mark.skipif(
    not _ON_TARGET, reason="requires the Linux+NVIDIA target box (real trainer)"
)
def test_fr10_real_finetune_on_target() -> None:
    """Real fine-tune verification stub (Linux + NVIDIA box only).

    On target hardware :func:`run_finetune` would invoke the real trainer
    (QLoRA on a single 24-48 GB GPU) instead of the deterministic simulation.
    Skipped off-target via the ``target_hardware`` marker + skipif guard, so the
    default dev machine never attempts GPU training.
    """
    pytest.skip("real GPU training is exercised only on the target box")
