"""Unit tests for model export and serving hand-off (FR-15)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.errors import GadziriroError, NotFound
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.modelstudio.base import ExportFormat, FineTuneMethod, TrainingSpec
from gadziriro.modelstudio.export import export_model, serving_command
from gadziriro.modelstudio.finetune import qlora_template, run_finetune
from gadziriro.registry.store import ObjectStoreRegistry
from gadziriro.tracking.store import ObjectStoreTracker


def _env(
    tmp_path: Path,
) -> tuple[ObjectStoreRegistry, ObjectStoreTracker, LocalObjectStore]:
    reg = ObjectStoreRegistry(LocalObjectStore(tmp_path / "registry"))
    tracker = ObjectStoreTracker(LocalObjectStore(tmp_path / "runs"))
    out_store = LocalObjectStore(tmp_path / "exports")
    return reg, tracker, out_store


def _trained_model_ref(reg: ObjectStoreRegistry, tracker: ObjectStoreTracker) -> str:
    reg.add_dataset(
        "patients", b"cohort", sensitivity=SensitivityLabel.PHI, source="ehr"
    )
    spec = TrainingSpec(
        base_model="llama-3-8b",
        method=FineTuneMethod.QLORA,
        dataset_refs=("patients@1",),
        output_name="clf",
        hyperparams=qlora_template(),
    )
    return run_finetune(reg, tracker, spec).model_ref


@pytest.mark.parametrize("fmt", list(ExportFormat))
def test_export_writes_blob_and_manifest(tmp_path: Path, fmt: ExportFormat) -> None:
    reg, tracker, out_store = _env(tmp_path)
    ref = _trained_model_ref(reg, tracker)

    artifact = export_model(reg, ref, fmt, out_store)

    # A blob landed in the export store under the expected key.
    assert artifact.path_or_key == f"exports/clf/1.{fmt.value}"
    assert out_store.exists(artifact.path_or_key)
    blob = out_store.get(artifact.path_or_key)
    assert fmt.value.encode() in blob  # header names the format
    # The serving manifest names the path + format for a deployer.
    manifest = artifact.serving_manifest
    assert manifest["format"] == fmt.value
    assert manifest["model_path"] == artifact.path_or_key
    assert manifest["model_ref"] == "clf@1"


def test_serving_command_vllm_and_tgi(tmp_path: Path) -> None:
    reg, tracker, out_store = _env(tmp_path)
    ref = _trained_model_ref(reg, tracker)
    artifact = export_model(reg, ref, ExportFormat.SAFETENSORS, out_store)

    vllm = serving_command(artifact, engine="vllm")
    assert "vllm.entrypoints.openai.api_server" in vllm
    assert "--model" in vllm
    assert artifact.path_or_key in vllm

    tgi = serving_command(artifact, engine="tgi")
    assert tgi[0] == "text-generation-launcher"
    assert "--model-id" in tgi
    assert artifact.path_or_key in tgi


def test_serving_command_rejects_unknown_engine(tmp_path: Path) -> None:
    reg, tracker, out_store = _env(tmp_path)
    ref = _trained_model_ref(reg, tracker)
    artifact = export_model(reg, ref, ExportFormat.ONNX, out_store)
    with pytest.raises(GadziriroError):
        serving_command(artifact, engine="triton")


def test_export_unknown_model_raises_notfound(tmp_path: Path) -> None:
    reg, _tracker, out_store = _env(tmp_path)
    with pytest.raises(NotFound):
        export_model(reg, "does-not-exist", ExportFormat.SAFETENSORS, out_store)


def test_export_latest_when_version_omitted(tmp_path: Path) -> None:
    reg, tracker, out_store = _env(tmp_path)
    _trained_model_ref(reg, tracker)
    _trained_model_ref(reg, tracker)  # clf@2 now latest (different run, same name)

    # Bare name -> latest version.
    artifact = export_model(reg, "clf", ExportFormat.GGUF, out_store)
    assert artifact.model_ref == "clf@2"
    assert artifact.path_or_key == "exports/clf/2.gguf"
