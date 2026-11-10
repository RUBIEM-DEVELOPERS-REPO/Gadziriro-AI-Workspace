"""Acceptance tests for FR-15: export a model and hand it off to a serving tool.

The requirement: a registered model exports to each supported format
(safetensors / GGUF / ONNX) and is handed off to an inference engine (vLLM or
TGI) via a serving manifest + command.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.modelstudio.base import ExportFormat, FineTuneMethod, TrainingSpec
from gadziriro.modelstudio.export import export_model, serving_command
from gadziriro.modelstudio.finetune import run_finetune, template_for
from gadziriro.registry.store import ObjectStoreRegistry
from gadziriro.tracking.store import ObjectStoreTracker


def _train(tmp_path: Path) -> tuple[ObjectStoreRegistry, LocalObjectStore, str]:
    reg = ObjectStoreRegistry(LocalObjectStore(tmp_path / "registry"))
    tracker = ObjectStoreTracker(LocalObjectStore(tmp_path / "runs"))
    out_store = LocalObjectStore(tmp_path / "exports")
    reg.add_dataset(
        "patients", b"cohort", sensitivity=SensitivityLabel.PHI, source="ehr"
    )
    spec = TrainingSpec(
        base_model="llama-3-8b",
        method=FineTuneMethod.QLORA,
        dataset_refs=("patients@1",),
        output_name="clf",
        hyperparams=template_for(FineTuneMethod.QLORA),
    )
    ref = run_finetune(reg, tracker, spec).model_ref
    return reg, out_store, ref


@pytest.mark.parametrize("fmt", list(ExportFormat))
def test_fr15_export_to_each_format(tmp_path: Path, fmt: ExportFormat) -> None:
    reg, out_store, ref = _train(tmp_path)

    artifact = export_model(reg, ref, fmt, out_store)

    # A concrete deployable blob exists.
    assert out_store.exists(artifact.path_or_key)
    assert artifact.fmt is fmt
    assert artifact.serving_manifest["format"] == fmt.value


def test_fr15_handoff_to_serving_tool(tmp_path: Path) -> None:
    reg, out_store, ref = _train(tmp_path)
    artifact = export_model(reg, ref, ExportFormat.SAFETENSORS, out_store)

    # Hand off to vLLM ...
    vllm = serving_command(artifact, engine="vllm")
    assert vllm[0] == "python"
    assert "--model" in vllm and artifact.path_or_key in vllm

    # ... or to TGI, both pointing at the exported artifact.
    tgi = serving_command(artifact, engine="tgi")
    assert tgi[0] == "text-generation-launcher"
    assert "--model-id" in tgi and artifact.path_or_key in tgi
