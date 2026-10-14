"""Weight tools: merge, quantize, prune, inspect (FR-12).

Phase 2 is mock-backed. These operations do **not** touch real tensors — they
perform deterministic, metadata-level transforms on the opaque model byte blobs
held by the registry. Each mutating op (:func:`merge`, :func:`quantize`,
:func:`prune`) produces a brand-new registered :class:`ModelVersion` whose
:class:`LineageRecord` points back at its source(s), so every derived artifact
stays traceable (and DSAR-reachable, FR-23) via lineage.

The transforms are pure functions of their inputs: the same source bytes and the
same parameters always yield the same output bytes, hence the same checksum.
This keeps tests stable across runs and stores.

Model bytes are read straight from the object store using the registry's
documented key layout (``models/<name>/<version>/blob``); the registry exposes
no public bytes accessor, so weight tools read the blob the same way the
registry itself persists it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from enum import Enum
from typing import Any, Optional

from ..core.crypto import sha256_hex
from ..core.errors import GadziriroError, NotFound
from ..governance.labels import SensitivityLabel
from ..registry.base import LineageRecord, ModelVersion
from ..registry.store import ObjectStoreRegistry


class QuantMethod(str, Enum):
    """Supported (simulated) quantization methods for :func:`quantize`."""

    GPTQ = "gptq"
    AWQ = "awq"
    GGUF = "gguf"


# Fraction of the original artifact retained by each method (smaller = heavier
# compression). Values are illustrative — this is a metadata-level simulation.
_QUANT_RETENTION: dict[QuantMethod, float] = {
    QuantMethod.GPTQ: 0.25,
    QuantMethod.AWQ: 0.30,
    QuantMethod.GGUF: 0.50,
}


# --------------------------------------------------------------------------- #
# internal helpers
# --------------------------------------------------------------------------- #
def _resolve(registry: ObjectStoreRegistry, ref: str) -> ModelVersion:
    """Resolve a ``"name"`` or ``"name@version"`` ref to a :class:`ModelVersion`.

    Raises :class:`NotFound` for an unknown name, an unknown version, or a
    malformed (non-integer) version suffix.
    """
    name, sep, version_str = ref.partition("@")
    if sep:
        try:
            version: Optional[int] = int(version_str)
        except ValueError as exc:
            raise NotFound(f"model not found: {ref}") from exc
    else:
        version = None
    return registry.get_model(name, version)


def _model_bytes(registry: ObjectStoreRegistry, model: ModelVersion) -> bytes:
    """Return the raw stored blob for ``model`` from the registry's object store."""
    key = f"models/{model.name}/{model.version}/blob"
    return registry._store.get(key)


def _with_meta(model: ModelVersion, extra: dict[str, Any]) -> ModelVersion:
    """Return a copy of ``model`` with ``extra`` merged into its ``meta``.

    The registry's ``add_model`` does not accept metadata, so op summaries (size
    reductions, source sizes) are attached to the returned object here. The
    persisted lineage ``params`` remain the durable, re-fetchable record.
    """
    merged = dict(model.meta)
    merged.update(extra)
    return replace(model, meta=merged)


def _union_dataset_refs(models: list[ModelVersion]) -> tuple[str, ...]:
    """Return the order-preserving union of every source's dataset refs."""
    seen: set[str] = set()
    out: list[str] = []
    for model in models:
        for ref in model.lineage.dataset_refs:
            if ref not in seen:
                seen.add(ref)
                out.append(ref)
    return tuple(out)


# --------------------------------------------------------------------------- #
# FR-12 operations
# --------------------------------------------------------------------------- #
def merge(
    registry: ObjectStoreRegistry,
    refs: list[str],
    out_name: str,
    *,
    weights: Optional[list[float]] = None,
) -> ModelVersion:
    """Merge two or more model versions into a new registered version.

    The merge is simulated: the source blobs are combined deterministically with
    a canonical header describing the sources and their blend ``weights`` (equal
    weights when ``None``). The new version's lineage carries
    ``params={"op": "merge", "sources": refs, "weights": weights}`` and the union
    of every source's ``dataset_refs``, and is labelled with the strictest source
    sensitivity (default-strict precedence).

    Raises :class:`GadziriroError` for fewer than two refs or a ``weights`` list
    whose length does not match ``refs``; :class:`NotFound` for an unknown ref.
    """
    if len(refs) < 2:
        raise GadziriroError("merge requires at least two source refs")
    if weights is not None and len(weights) != len(refs):
        raise GadziriroError("weights length must match the number of refs")

    sources = [_resolve(registry, ref) for ref in refs]
    blobs = [_model_bytes(registry, model) for model in sources]

    spec = json.dumps(
        {"sources": list(refs), "weights": weights}, sort_keys=True
    ).encode("utf-8")
    merged = b"GADZMERGE1:" + spec + b":" + b"\x00".join(blobs)

    lineage = LineageRecord(
        dataset_refs=_union_dataset_refs(sources),
        code_ref="weighttools.merge",
        params={"op": "merge", "sources": list(refs), "weights": weights},
        hardware="mock",
        run_id=f"merge-{sha256_hex(merged)[:12]}",
    )
    sensitivity = SensitivityLabel.strictest([m.sensitivity for m in sources])
    model = registry.add_model(
        out_name, merged, lineage=lineage, sensitivity=sensitivity
    )
    return _with_meta(
        model,
        {
            "op": "merge",
            "sources": list(refs),
            "weights": weights,
            "source_bytes": [len(b) for b in blobs],
            "merged_bytes": len(merged),
        },
    )


def quantize(
    registry: ObjectStoreRegistry,
    ref: str,
    method: QuantMethod,
    out_name: str,
) -> ModelVersion:
    """Quantize a model version into a new, smaller registered version.

    The shrink is simulated: the artifact is reduced to a method-specific
    fraction of its original size and tagged with the method. Lineage carries
    ``params={"op": "quantize", "method": method.value, "source": ref}`` and the
    source's ``dataset_refs`` (so traceability and DSAR reach survive). The
    returned object's ``meta`` records the approximate size reduction.

    Raises :class:`NotFound` for an unknown ``ref``.
    """
    source = _resolve(registry, ref)
    blob = _model_bytes(registry, source)

    retention = _QUANT_RETENTION[method]
    keep = max(1, int(len(blob) * retention))
    new_blob = f"GADZQUANT:{method.value}:".encode("utf-8") + blob[:keep]

    original_bytes = len(blob)
    quantized_bytes = len(new_blob)
    reduction = 1.0 - (quantized_bytes / original_bytes) if original_bytes else 0.0

    lineage = LineageRecord(
        dataset_refs=source.lineage.dataset_refs,
        code_ref="weighttools.quantize",
        params={"op": "quantize", "method": method.value, "source": ref},
        hardware="mock",
        run_id=f"quant-{sha256_hex(new_blob)[:12]}",
    )
    model = registry.add_model(
        out_name, new_blob, lineage=lineage, sensitivity=source.sensitivity
    )
    return _with_meta(
        model,
        {
            "op": "quantize",
            "method": method.value,
            "source": ref,
            "original_bytes": original_bytes,
            "quantized_bytes": quantized_bytes,
            "size_reduction": round(reduction, 4),
        },
    )


def prune(
    registry: ObjectStoreRegistry,
    ref: str,
    sparsity: float,
    out_name: str,
) -> ModelVersion:
    """Prune a model version at a given ``sparsity`` into a new registered version.

    The trim is simulated: a ``sparsity`` fraction (``0..1``) of the artifact is
    dropped deterministically. Lineage carries
    ``params={"op": "prune", "sparsity": sparsity, "source": ref}`` and the
    source's ``dataset_refs``. The returned object's ``meta`` records the
    retained fraction.

    Raises :class:`GadziriroError` if ``sparsity`` is outside ``[0, 1]`` and
    :class:`NotFound` for an unknown ``ref``.
    """
    if not 0.0 <= sparsity <= 1.0:
        raise GadziriroError("sparsity must be between 0 and 1 inclusive")

    source = _resolve(registry, ref)
    blob = _model_bytes(registry, source)

    keep = max(1, int(round(len(blob) * (1.0 - sparsity))))
    new_blob = f"GADZPRUNE:{sparsity}:".encode("utf-8") + blob[:keep]

    lineage = LineageRecord(
        dataset_refs=source.lineage.dataset_refs,
        code_ref="weighttools.prune",
        params={"op": "prune", "sparsity": sparsity, "source": ref},
        hardware="mock",
        run_id=f"prune-{sha256_hex(new_blob)[:12]}",
    )
    model = registry.add_model(
        out_name, new_blob, lineage=lineage, sensitivity=source.sensitivity
    )
    retained = (keep / len(blob)) if blob else 0.0
    return _with_meta(
        model,
        {
            "op": "prune",
            "sparsity": sparsity,
            "source": ref,
            "original_bytes": len(blob),
            "pruned_bytes": len(new_blob),
            "retained": round(retained, 4),
        },
    )


def inspect(registry: ObjectStoreRegistry, ref: str) -> dict[str, Any]:
    """Return a deterministic summary of a model version's artifact.

    The summary includes the artifact size in bytes, its checksum, a simulated
    layer list / parameter count derived deterministically from the checksum
    (itself the hash of the bytes), and the lineage ``op`` that produced the
    version (``None`` for a base model registered directly).

    Raises :class:`NotFound` for an unknown ``ref``.
    """
    model = _resolve(registry, ref)
    blob = _model_bytes(registry, model)

    checksum = model.checksum
    seed = int(checksum[:8], 16)
    num_layers = (seed % 12) + 1
    layers: list[dict[str, Any]] = []
    for i in range(num_layers):
        start = (i * 4) % 56
        chunk = checksum[start : start + 4] or "0"
        params = int(chunk, 16) + 1
        layers.append({"name": f"layer_{i}", "params": params})

    return {
        "ref": model.ref,
        "name": model.name,
        "version": model.version,
        "size_bytes": len(blob),
        "checksum": checksum,
        "sensitivity": model.sensitivity.value,
        "num_layers": num_layers,
        "layers": layers,
        "param_count": sum(layer["params"] for layer in layers),
        "op": model.lineage.params.get("op"),
    }
