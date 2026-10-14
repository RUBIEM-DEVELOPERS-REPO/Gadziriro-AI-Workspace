"""Model export + serving hand-off (FR-15).

Takes a registered model and produces a deployable artifact in one of the
supported :class:`~gadziriro.modelstudio.base.ExportFormat` values, plus a
serving manifest that hands the model off to an inference engine (vLLM or TGI).

Phase 2 is mock-backed: the "conversion" is simulated. We never shell out to a
real safetensors/GGUF/ONNX converter — instead the exported blob wraps a small
header (naming the format and the source model) around a canonical payload
derived from the registered model. The exported blob is written to a
:class:`~gadziriro.core.objectstore.LocalObjectStore` under a stable key so the
registry store and the export store stay separate concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..core.canonical_json import canonical_bytes
from ..core.errors import GadziriroError
from ..core.objectstore import ObjectStore
from ..registry.base import ModelVersion
from ..registry.store import ObjectStoreRegistry
from .base import ExportFormat

_EXPORTS = "exports"

#: Suggested default serving arguments per engine, keyed by export format.
#: These are plausible hand-off defaults, not an exhaustive tuning surface.
_SERVING_DEFAULTS: dict[str, dict[str, Any]] = {
    "vllm": {
        "dtype": "bfloat16",
        "max_model_len": 4096,
        "gpu_memory_utilization": 0.90,
    },
    "tgi": {
        "dtype": "bfloat16",
        "max_input_length": 4096,
        "max_total_tokens": 8192,
    },
}


@dataclass(frozen=True)
class ExportArtifact:
    """A materialised export plus the manifest that serves it (FR-15)."""

    model_ref: str  # "name@version" that was exported
    fmt: ExportFormat
    path_or_key: str  # object-store key of the exported blob
    serving_manifest: dict[str, Any] = field(default_factory=dict)


def _parse_ref(model_ref: str) -> tuple[str, Optional[int]]:
    """Split ``"name@version"`` into ``(name, version)`` (``None`` = latest).

    A bare ``"name"`` resolves to the latest version. A malformed version
    component raises :class:`GadziriroError`.
    """
    name, sep, version = model_ref.rpartition("@")
    if not sep:
        return model_ref, None
    try:
        return name, int(version)
    except ValueError as exc:
        raise GadziriroError(f"invalid model ref: {model_ref!r}") from exc


def _export_key(model: ModelVersion, fmt: ExportFormat) -> str:
    """Return the object-store key for an exported blob of ``model``/``fmt``."""
    return f"{_EXPORTS}/{model.name}/{model.version}.{fmt.value}"


def _exported_blob(model: ModelVersion, fmt: ExportFormat) -> bytes:
    """Build the (simulated) exported blob: a format header wrapping the payload.

    The header names the target format and the exact source model/checksum so a
    deployer can verify provenance; the payload is a canonical rendering of the
    model's identity and lineage standing in for converted weights.
    """
    header = {
        "gadziriro_export": "v1",
        "format": fmt.value,
        "model_ref": model.ref,
        "source_checksum": model.checksum,
    }
    payload = {
        "ref": model.ref,
        "checksum": model.checksum,
        "lineage": {
            "dataset_refs": list(model.lineage.dataset_refs),
            "code_ref": model.lineage.code_ref,
            "run_id": model.lineage.run_id,
            "hardware": model.lineage.hardware,
        },
    }
    return canonical_bytes(header) + b"\n" + canonical_bytes(payload)


def _serving_manifest(
    model: ModelVersion, fmt: ExportFormat, path_or_key: str
) -> dict[str, Any]:
    """Build the vLLM / TGI serving hand-off manifest (FR-15)."""
    return {
        "served_model_name": model.name,
        "model_ref": model.ref,
        "model_path": path_or_key,
        "format": fmt.value,
        "source_checksum": model.checksum,
        "engines": {
            "vllm": dict(_SERVING_DEFAULTS["vllm"]),
            "tgi": dict(_SERVING_DEFAULTS["tgi"]),
        },
    }


def export_model(
    registry: ObjectStoreRegistry,
    model_ref: str,
    fmt: ExportFormat,
    out_store: ObjectStore,
) -> ExportArtifact:
    """Export a registered model to ``fmt`` and build its serving hand-off (FR-15).

    Loads ``model_ref`` from ``registry`` (``NotFound`` if it does not exist),
    writes a simulated exported blob into ``out_store`` under
    ``exports/<name>/<version>.<fmt>``, and returns an :class:`ExportArtifact`
    carrying the object-store key and a vLLM/TGI serving manifest.
    """
    name, version = _parse_ref(model_ref)
    model = registry.get_model(name, version)  # raises NotFound for unknown models

    key = _export_key(model, fmt)
    out_store.put(key, _exported_blob(model, fmt))

    manifest = _serving_manifest(model, fmt, key)
    return ExportArtifact(
        model_ref=model.ref,
        fmt=fmt,
        path_or_key=key,
        serving_manifest=manifest,
    )


def serving_command(artifact: ExportArtifact, engine: str = "vllm") -> list[str]:
    """Return a plausible serving command for ``artifact`` (FR-15 hand-off).

    ``engine`` is ``"vllm"`` or ``"tgi"``. The command is a hand-off stub an
    operator (or a Phase 3 orchestrator) would run to serve the exported model;
    it is built from the serving manifest, not hard-coded.
    """
    engine = engine.lower()
    manifest = artifact.serving_manifest
    path = manifest["model_path"]

    if engine == "vllm":
        args = manifest["engines"]["vllm"]
        return [
            "python",
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--model",
            path,
            "--served-model-name",
            manifest["served_model_name"],
            "--dtype",
            str(args["dtype"]),
            "--max-model-len",
            str(args["max_model_len"]),
            "--gpu-memory-utilization",
            str(args["gpu_memory_utilization"]),
        ]
    if engine == "tgi":
        args = manifest["engines"]["tgi"]
        return [
            "text-generation-launcher",
            "--model-id",
            path,
            "--dtype",
            str(args["dtype"]),
            "--max-input-length",
            str(args["max_input_length"]),
            "--max-total-tokens",
            str(args["max_total_tokens"]),
        ]
    raise GadziriroError(f"unsupported serving engine: {engine!r}")
