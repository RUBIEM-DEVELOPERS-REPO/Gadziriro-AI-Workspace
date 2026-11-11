"""Admin reports — admin or compliance.

* ``GET /api/reports/egress`` — "what left this machine" (FR-25); optional
  ``?since=<ISO timestamp>``.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends

from ...auth.base import Principal, Role
from ...reporting.egress_report import build_egress_report
from ..deps import get_audit, require_any_role
from ..registry import register_router

router = APIRouter(tags=["reports"])

_require_admin_or_compliance = require_any_role(Role.ADMIN, Role.COMPLIANCE)


@router.get("/egress")
def egress_report(
    audit: Annotated[Any, Depends(get_audit)],
    _: Annotated[Principal, Depends(_require_admin_or_compliance)],
    since: Optional[str] = None,
) -> dict[str, Any]:
    """Summarise transfer-relevant audit events as an egress report."""
    return asdict(build_egress_report(audit, since=since))


register_router("/api/reports", router)
