"""Incident-response routes (FR-38) — admin / compliance only.

Drives the shared :class:`~gadziriro.incident.response.IncidentService` singleton
(wired onto ``app.state``) through an audited lifecycle and produces a draft
breach-notification report from the tamper-evident audit log:

* ``POST /api/incidents`` — open an incident.
* ``GET /api/incidents`` — list incidents.
* ``POST /api/incidents/{id}/update`` — change status and/or add a note.
* ``GET /api/incidents/{id}/breach-report`` — build the draft breach report.

Every route requires :data:`Role.ADMIN` or :data:`Role.COMPLIANCE`.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ...audit.log import AuditLog
from ...auth.base import Principal, Role
from ...core.errors import GadziriroError
from ...incident.response import IncidentService, build_breach_report
from ..deps import get_incident_service, require_any_role
from ..registry import register_router

router = APIRouter(tags=["incidents"])

_require_admin_or_compliance = require_any_role(Role.ADMIN, Role.COMPLIANCE)


class OpenIncidentIn(BaseModel):
    """Body for opening an incident."""

    title: str
    severity: str = "medium"
    breach: bool = False
    affected_subjects: list[str] = Field(default_factory=list)


class UpdateIncidentIn(BaseModel):
    """Body for updating an incident (status and/or note)."""

    status: Optional[str] = None
    note: Optional[str] = None


@router.post("")
def open_incident(
    body: OpenIncidentIn,
    service: Annotated[IncidentService, Depends(get_incident_service)],
    _: Annotated[Principal, Depends(_require_admin_or_compliance)],
) -> dict[str, Any]:
    """Open a new incident and audit it (FR-38)."""
    incident = service.open_incident(
        body.title,
        body.severity,
        breach=body.breach,
        affected_subjects=tuple(body.affected_subjects),
    )
    return incident.to_dict()


@router.get("")
def list_incidents(
    service: Annotated[IncidentService, Depends(get_incident_service)],
    _: Annotated[Principal, Depends(_require_admin_or_compliance)],
) -> list[dict[str, Any]]:
    """List every tracked incident, oldest first (FR-38)."""
    return [incident.to_dict() for incident in service.list_incidents()]


@router.post("/{incident_id}/update")
def update_incident(
    incident_id: str,
    body: UpdateIncidentIn,
    service: Annotated[IncidentService, Depends(get_incident_service)],
    _: Annotated[Principal, Depends(_require_admin_or_compliance)],
) -> dict[str, Any]:
    """Update an incident's status and/or append a note (FR-38).

    :raises NotFound: if the incident is unknown (404).
    :raises GadziriroError: if ``status`` is not a valid lifecycle state (400).
    """
    try:
        incident = service.update_incident(
            incident_id, status=body.status, note=body.note
        )
    except ValueError as exc:
        raise GadziriroError(str(exc)) from exc
    return incident.to_dict()


@router.get("/{incident_id}/breach-report")
def breach_report(
    incident_id: str,
    request: Request,
    service: Annotated[IncidentService, Depends(get_incident_service)],
    _: Annotated[Principal, Depends(_require_admin_or_compliance)],
) -> dict[str, Any]:
    """Build the draft breach-notification report for an incident (FR-38).

    :raises NotFound: if the incident is unknown (404).
    """
    incident = service.get_incident(incident_id)
    audit = request.app.state.audit
    if not isinstance(audit, AuditLog):
        raise GadziriroError("breach report requires a file-backed audit log")
    return build_breach_report(incident, audit)


register_router("/api/incidents", router)
