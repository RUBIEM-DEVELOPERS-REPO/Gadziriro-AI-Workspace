"""Audit routes (FR-19) — chain verification (admin-only).

``GET /api/audit/verify`` recomputes the audit hash chain and returns an
:class:`AuditVerifyOut`. Restricted to :data:`Role.ADMIN`; a non-admin is
refused with HTTP 403.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ...auth.base import Principal, Role
from ..deps import get_audit, require_role
from ..registry import register_router
from ..schemas import AuditVerifyOut

router = APIRouter(tags=["audit"])


@router.get("/verify", response_model=AuditVerifyOut)
def verify(
    request: Request,
    _: Annotated[Principal, Depends(require_role(Role.ADMIN))],
) -> AuditVerifyOut:
    """Verify the audit chain and report the first break, if any."""
    result = get_audit(request).verify()
    return AuditVerifyOut(
        ok=result.ok,
        count=result.count,
        broken_at=result.broken_at,
        detail=result.detail,
    )


register_router("/api/audit", router)
