"""Model Studio routes (FR-10, FR-15) — fine-tune, export, templates.

Surfaces the Phase 2 Model Studio engine over the injected registry + tracker +
shared object store:

* ``POST /api/modelstudio/finetune`` — launch a (mock) fine-tune from a form
  (the same engine the engineer reaches in code) and register the result.
* ``POST /api/modelstudio/export`` — export a registered model to a deployable
  format and return the artifact plus a serving hand-off command.
* ``GET /api/modelstudio/templates`` — the per-method hyper-parameter templates.

Every route requires an authenticated principal.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...auth.base import Principal
from ...core.errors import GadziriroError
from ...modelstudio.base import ExportFormat, FineTuneMethod, TrainingResult
from ...modelstudio.export import ExportArtifact, export_model, serving_command
from ...modelstudio.finetune import run_finetune, spec_from_form, template_for
from ...registry.store import ObjectStoreRegistry
from ...tracking.store import ObjectStoreTracker
from ..deps import get_current_principal, get_object_store, get_registry, get_tracker
from ..registry import register_router

router = APIRouter(tags=["modelstudio"])


class FineTuneIn(BaseModel):
    """Body for launching a fine-tune (analyst form / engineer payload)."""

    base_model: str
    dataset_refs: list[str]
    output_name: str
    method: Optional[str] = None
    hyperparams: dict[str, Any] = Field(default_factory=dict)
    hardware: Optional[str] = None
    code_ref: Optional[str] = None


class ExportIn(BaseModel):
    """Body for exporting a registered model (FR-15)."""

    model_ref: str
    format: str
    engine: str = "vllm"


def _result_to_dict(result: TrainingResult) -> dict[str, Any]:
    """Project a :class:`TrainingResult` onto a JSON-serialisable dict."""
    return {
        "model_ref": result.model_ref,
        "run_id": result.run_id,
        "method": result.method.value,
        "base_model": result.base_model,
        "metrics": dict(result.metrics),
    }


def _artifact_to_dict(artifact: ExportArtifact, engine: str) -> dict[str, Any]:
    """Project an :class:`ExportArtifact` plus its serving command onto a dict."""
    return {
        "model_ref": artifact.model_ref,
        "format": artifact.fmt.value,
        "path_or_key": artifact.path_or_key,
        "serving_manifest": artifact.serving_manifest,
        "serving_command": serving_command(artifact, engine),
    }


@router.post("/finetune")
def finetune(
    body: FineTuneIn,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    tracker: Annotated[ObjectStoreTracker, Depends(get_tracker)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Run a (mock) fine-tune and register the resulting model (FR-10).

    :raises GadziriroError: for a malformed form (e.g. unknown method) — HTTP 400.
    """
    form: dict[str, Any] = {
        "base_model": body.base_model,
        "dataset_refs": body.dataset_refs,
        "output_name": body.output_name,
        "hyperparams": body.hyperparams,
    }
    if body.method is not None:
        form["method"] = body.method
    if body.hardware is not None:
        form["hardware"] = body.hardware
    if body.code_ref is not None:
        form["code_ref"] = body.code_ref

    try:
        spec = spec_from_form(form)
    except (ValueError, KeyError) as exc:
        raise GadziriroError(f"invalid fine-tune form: {exc}") from exc

    return _result_to_dict(run_finetune(registry, tracker, spec))


@router.post("/export")
def export(
    body: ExportIn,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    store: Annotated[Any, Depends(get_object_store)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Export a registered model and return the artifact + serving command (FR-15).

    :raises GadziriroError: for an unknown export format (HTTP 400).
    :raises NotFound: if the model does not exist (HTTP 404).
    """
    try:
        fmt = ExportFormat(body.format.lower())
    except ValueError as exc:
        raise GadziriroError(f"unknown export format: {body.format!r}") from exc

    artifact = export_model(registry, body.model_ref, fmt, store)
    return _artifact_to_dict(artifact, body.engine)


@router.get("/templates")
def templates(
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Return the per-method fine-tune hyper-parameter templates (FR-10)."""
    return {
        "methods": [m.value for m in FineTuneMethod],
        "templates": {m.value: template_for(m) for m in FineTuneMethod},
    }


register_router("/api/modelstudio", router)
