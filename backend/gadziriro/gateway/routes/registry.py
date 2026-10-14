"""Dataset & model registry routes (FR-06, FR-07) — versions + lineage.

Read-only views over the injected
:class:`~gadziriro.registry.store.ObjectStoreRegistry`:
list datasets/models, inspect every version of one, and resolve a single model
version together with the :class:`~gadziriro.registry.base.LineageRecord` that
produced it (the source of truth for reproducibility and DSAR). Every route
requires an authenticated principal.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from ...auth.base import Principal
from ...registry.base import DatasetVersion, ModelVersion
from ...registry.store import ObjectStoreRegistry
from ..deps import get_current_principal, get_object_store, get_registry
from ..registry import register_router

router = APIRouter(tags=["registry"])

_DATASETS = "datasets"
_MODELS = "models"


def _dataset_to_dict(dv: DatasetVersion) -> dict[str, Any]:
    """Project a :class:`DatasetVersion` onto a JSON-serialisable dict."""
    return {
        "name": dv.name,
        "version": dv.version,
        "ref": dv.ref,
        "sensitivity": dv.sensitivity.value,
        "source": dv.source,
        "checksum": dv.checksum,
        "created_at": dv.created_at,
        "subjects": list(dv.subjects),
    }


def _model_to_dict(mv: ModelVersion) -> dict[str, Any]:
    """Project a :class:`ModelVersion` (incl. lineage) onto a dict."""
    return {
        "name": mv.name,
        "version": mv.version,
        "ref": mv.ref,
        "checksum": mv.checksum,
        "created_at": mv.created_at,
        "sensitivity": mv.sensitivity.value,
        "flagged": mv.flagged,
        "lineage": {
            "dataset_refs": list(mv.lineage.dataset_refs),
            "code_ref": mv.lineage.code_ref,
            "params": dict(mv.lineage.params),
            "hardware": mv.lineage.hardware,
            "run_id": mv.lineage.run_id,
        },
    }


def _names(store: Any, kind: str) -> list[str]:
    """Return the registered resource names of ``kind`` from the object store."""
    return list(store.iter_prefixes(kind))


@router.get("/datasets")
def list_datasets(
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    store: Annotated[Any, Depends(get_object_store)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> list[dict[str, Any]]:
    """List every dataset with its versions (latest first per name)."""
    out: list[dict[str, Any]] = []
    for name in _names(store, _DATASETS):
        versions = registry.list_dataset_versions(name)
        out.append(
            {
                "name": name,
                "versions": [_dataset_to_dict(v) for v in versions],
                "latest": versions[-1].version if versions else None,
            }
        )
    return out


@router.get("/datasets/{name}")
def get_dataset(
    name: str,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Return every version of dataset ``name``.

    :raises NotFound: if the dataset does not exist (mapped to HTTP 404).
    """
    versions = registry.list_dataset_versions(name)
    return {
        "name": name,
        "versions": [_dataset_to_dict(v) for v in versions],
    }


@router.get("/models")
def list_models(
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    store: Annotated[Any, Depends(get_object_store)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> list[dict[str, Any]]:
    """List every model with its versions."""
    out: list[dict[str, Any]] = []
    for name in _names(store, _MODELS):
        versions = registry.list_model_versions(name)
        out.append(
            {
                "name": name,
                "versions": [_model_to_dict(v) for v in versions],
                "latest": versions[-1].version if versions else None,
            }
        )
    return out


@router.get("/models/{name}")
def get_model(
    name: str,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Return every version of model ``name`` with lineage."""
    versions = registry.list_model_versions(name)
    return {
        "name": name,
        "versions": [_model_to_dict(v) for v in versions],
    }


@router.get("/models/{name}/{version}")
def get_model_version(
    name: str,
    version: int,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Return one model version and its lineage.

    :raises NotFound: if the model/version does not exist (mapped to HTTP 404).
    """
    return _model_to_dict(registry.get_model(name, version))


register_router("/api", router)
