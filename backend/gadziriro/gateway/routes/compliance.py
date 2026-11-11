"""Compliance routes (FR-46, FR-47) — compliance or admin.

* ``GET /api/compliance/ropa`` — build + export the ROPA register.
* ``POST /api/compliance/dpia`` / ``GET /api/compliance/dpia`` /
  ``GET /api/compliance/dpia/{id}`` — DPIA create / list / read.
* ``POST /api/compliance/dpia/{id}/status`` — move through the lifecycle.
* ``POST /api/compliance/dpia/{id}/risk`` — add a risk.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...auth.base import Principal, Role
from ...compliance.dpia import DpiaRisk, DpiaService
from ...compliance.ropa import build_ropa, export_ropa
from ..deps import get_dpia_service, get_object_store, get_registry, require_any_role
from ..registry import register_router

router = APIRouter(tags=["compliance"])

_require_compliance_or_admin = require_any_role(Role.COMPLIANCE, Role.ADMIN)


class DpiaIn(BaseModel):
    """Body for creating a DPIA."""

    title: str
    scope: str = ""
    from_template: bool = True


class DpiaStatusIn(BaseModel):
    """Body for a DPIA status change."""

    status: str


class DpiaRiskIn(BaseModel):
    """Body for adding a DPIA risk."""

    description: str
    likelihood: str
    impact: str
    mitigation: str
    residual: str


@router.get("/ropa")
def ropa(
    registry: Annotated[Any, Depends(get_registry)],
    store: Annotated[Any, Depends(get_object_store)],
    _: Annotated[Principal, Depends(_require_compliance_or_admin)],
) -> dict[str, Any]:
    """Build the ROPA from personal-data datasets, export it, return the register."""
    activities = build_ropa(registry, store)
    key = export_ropa(activities, store)
    return {"export_key": key, "activities": [asdict(a) for a in activities]}


@router.post("/dpia")
def create_dpia(
    body: DpiaIn,
    service: Annotated[DpiaService, Depends(get_dpia_service)],
    principal: Annotated[Principal, Depends(_require_compliance_or_admin)],
) -> dict[str, Any]:
    """Create a DPIA (assessor = the calling user)."""
    dpia = service.create_dpia(
        body.title, body.scope, principal.username, from_template=body.from_template
    )
    return asdict(dpia)


@router.get("/dpia")
def list_dpias(
    service: Annotated[DpiaService, Depends(get_dpia_service)],
    _: Annotated[Principal, Depends(_require_compliance_or_admin)],
) -> list[dict[str, Any]]:
    """List every DPIA."""
    return [asdict(d) for d in service.list_dpias()]


@router.get("/dpia/{dpia_id}")
def get_dpia(
    dpia_id: str,
    service: Annotated[DpiaService, Depends(get_dpia_service)],
    _: Annotated[Principal, Depends(_require_compliance_or_admin)],
) -> dict[str, Any]:
    """Read one DPIA (404 if unknown)."""
    return asdict(service.get(dpia_id))


@router.post("/dpia/{dpia_id}/status")
def set_dpia_status(
    dpia_id: str,
    body: DpiaStatusIn,
    service: Annotated[DpiaService, Depends(get_dpia_service)],
    _: Annotated[Principal, Depends(_require_compliance_or_admin)],
) -> dict[str, Any]:
    """Change DPIA status (400 on an invalid transition)."""
    return asdict(service.set_status(dpia_id, body.status))


@router.post("/dpia/{dpia_id}/risk")
def add_dpia_risk(
    dpia_id: str,
    body: DpiaRiskIn,
    service: Annotated[DpiaService, Depends(get_dpia_service)],
    _: Annotated[Principal, Depends(_require_compliance_or_admin)],
) -> dict[str, Any]:
    """Add a risk to a DPIA."""
    return asdict(service.add_risk(dpia_id, DpiaRisk(**body.model_dump())))


register_router("/api/compliance", router)
