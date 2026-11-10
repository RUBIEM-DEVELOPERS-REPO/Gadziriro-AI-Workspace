"""Weight-tools routes (FR-12) — merge, quantize, prune, inspect.

Metadata-level (mock) weight operations over the injected registry. Each mutating
op registers a brand-new, lineage-traceable model version. Mutating routes are
restricted to :data:`Role.DATA_SCIENTIST` or :data:`Role.ADMIN`; inspect only
requires those roles too (it reveals artifact internals).
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...auth.base import Principal, Role
from ...core.errors import GadziriroError
from ...registry.base import ModelVersion
from ...registry.store import ObjectStoreRegistry
from ...weighttools.ops import QuantMethod, inspect, merge, prune, quantize
from ..deps import get_registry, require_any_role
from ..registry import register_router

router = APIRouter(tags=["weighttools"])

_require_ds = require_any_role(Role.DATA_SCIENTIST, Role.ADMIN)


class MergeIn(BaseModel):
    """Body for merging two or more model versions."""

    refs: list[str]
    out_name: str
    weights: Optional[list[float]] = None


class QuantizeIn(BaseModel):
    """Body for quantizing a model version."""

    ref: str
    method: str
    out_name: str


class PruneIn(BaseModel):
    """Body for pruning a model version at a given sparsity."""

    ref: str
    sparsity: float
    out_name: str


def _model_to_dict(model: ModelVersion) -> dict[str, Any]:
    """Project a :class:`ModelVersion` (incl. op meta + lineage) onto a dict."""
    return {
        "name": model.name,
        "version": model.version,
        "ref": model.ref,
        "checksum": model.checksum,
        "sensitivity": model.sensitivity.value,
        "flagged": model.flagged,
        "meta": dict(model.meta),
        "lineage": {
            "dataset_refs": list(model.lineage.dataset_refs),
            "code_ref": model.lineage.code_ref,
            "params": dict(model.lineage.params),
            "hardware": model.lineage.hardware,
            "run_id": model.lineage.run_id,
        },
    }


@router.post("/merge")
def merge_models(
    body: MergeIn,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    _: Annotated[Principal, Depends(_require_ds)],
) -> dict[str, Any]:
    """Merge model versions into a new registered version (FR-12).

    :raises GadziriroError: for fewer than two refs or a bad weights list (400).
    :raises NotFound: if a source ref is unknown (404).
    """
    merged = merge(registry, body.refs, body.out_name, weights=body.weights)
    return _model_to_dict(merged)


@router.post("/quantize")
def quantize_model(
    body: QuantizeIn,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    _: Annotated[Principal, Depends(_require_ds)],
) -> dict[str, Any]:
    """Quantize a model version into a new, smaller registered version (FR-12).

    :raises GadziriroError: for an unknown quantization method (400).
    :raises NotFound: if the source ref is unknown (404).
    """
    try:
        method = QuantMethod(body.method.lower())
    except ValueError as exc:
        raise GadziriroError(f"unknown quantization method: {body.method!r}") from exc
    return _model_to_dict(quantize(registry, body.ref, method, body.out_name))


@router.post("/prune")
def prune_model(
    body: PruneIn,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    _: Annotated[Principal, Depends(_require_ds)],
) -> dict[str, Any]:
    """Prune a model version at a given sparsity into a new version (FR-12).

    :raises GadziriroError: if ``sparsity`` is outside ``[0, 1]`` (400).
    :raises NotFound: if the source ref is unknown (404).
    """
    return _model_to_dict(prune(registry, body.ref, body.sparsity, body.out_name))


@router.get("/inspect/{name}/{version}")
def inspect_model(
    name: str,
    version: int,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    _: Annotated[Principal, Depends(_require_ds)],
) -> dict[str, Any]:
    """Return a deterministic summary of a model version's artifact (FR-12).

    :raises NotFound: if the model/version does not exist (404).
    """
    return inspect(registry, f"{name}@{version}")


register_router("/api/weighttools", router)
