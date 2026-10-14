"""Model Studio shared contracts (fine-tune specs, results, export formats).

Phase 2 is mock-backed: a "training run" does not touch a real GPU — it records a
reproducible TrainingSpec, produces a model artifact, and registers it with
lineage + a tracker run. Real fine-tuning is a target-hardware concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FineTuneMethod(str, Enum):
    LORA = "lora"
    QLORA = "qlora"  # default on one 24-48 GB GPU (BRD O3/NFR-07)
    FULL = "full"


class ExportFormat(str, Enum):
    SAFETENSORS = "safetensors"
    GGUF = "gguf"
    ONNX = "onnx"


@dataclass(frozen=True)
class TrainingSpec:
    """Everything needed to reproduce a fine-tune (FR-09/FR-10)."""

    base_model: str
    method: FineTuneMethod
    dataset_refs: tuple[str, ...]
    output_name: str
    hyperparams: dict[str, Any] = field(default_factory=dict)
    hardware: str = "mock"
    code_ref: str = ""


@dataclass(frozen=True)
class TrainingResult:
    """Outcome of a (simulated) fine-tune."""

    model_ref: str  # "name@version" in the registry
    run_id: str  # tracker run id
    method: FineTuneMethod
    base_model: str
    metrics: dict[str, Any] = field(default_factory=dict)
