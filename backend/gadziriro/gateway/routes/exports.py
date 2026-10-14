"""Export-approval routes (FR-21).

``POST /api/exports`` opens an export request for the caller (auto-approved for
PUBLIC/INTERNAL, pending for PERSONAL/PHI); ``GET /api/exports`` lists requests;
``POST /api/exports/{id}/approve`` and ``POST /api/exports/{id}/deny`` are the
admin decision routes. Every state change is audited by the policy itself.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...auth.base import Principal, Role
from ...policy.exports import ExportPolicy, ExportRequest
from ..deps import get_current_principal, get_export_policy, require_role
from ..registry import register_router

router = APIRouter(tags=["exports"])


class RequestExportIn(BaseModel):
    """Body for requesting an export."""

    resource_ref: str
    sensitivity: str


class DenyExportIn(BaseModel):
    """Body for denying an export request."""

    reason: str = ""


def _request_to_dict(req: ExportRequest) -> dict[str, Any]:
    """Project an :class:`ExportRequest` onto a JSON-serialisable dict."""
    return {
        "request_id": req.request_id,
        "resource_ref": req.resource_ref,
        "sensitivity": req.sensitivity.value,
        "requested_by": req.requested_by,
        "status": req.status,
        "created_at": req.created_at,
        "decided_by": req.decided_by,
        "decided_at": req.decided_at,
        "reason": req.reason,
    }


@router.post("")
def request_export(
    body: RequestExportIn,
    policy: Annotated[ExportPolicy, Depends(get_export_policy)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Open an export request for the caller (FR-21)."""
    req = policy.request_export(body.resource_ref, body.sensitivity, principal.username)
    return _request_to_dict(req)


@router.get("")
def list_exports(
    policy: Annotated[ExportPolicy, Depends(get_export_policy)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> list[dict[str, Any]]:
    """List every export request."""
    return [_request_to_dict(req) for req in policy.list_requests()]


@router.post("/{request_id}/approve")
def approve_export(
    request_id: str,
    policy: Annotated[ExportPolicy, Depends(get_export_policy)],
    principal: Annotated[Principal, Depends(require_role(Role.ADMIN))],
) -> dict[str, Any]:
    """Approve a pending export request (admin only).

    :raises NotFound: if the request is unknown (HTTP 404).
    :raises PolicyDenied: if the request is not pending (HTTP 403).
    """
    return _request_to_dict(policy.approve(request_id, principal.username))


@router.post("/{request_id}/deny")
def deny_export(
    request_id: str,
    body: DenyExportIn,
    policy: Annotated[ExportPolicy, Depends(get_export_policy)],
    principal: Annotated[Principal, Depends(require_role(Role.ADMIN))],
) -> dict[str, Any]:
    """Deny a pending export request (admin only).

    :raises NotFound: if the request is unknown (HTTP 404).
    :raises PolicyDenied: if the request is not pending (HTTP 403).
    """
    return _request_to_dict(policy.deny(request_id, principal.username, body.reason))


register_router("/api/exports", router)
