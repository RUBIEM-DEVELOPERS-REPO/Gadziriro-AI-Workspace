"""Installer routes (FR-27) — host hardware report.

``GET /api/installer/hardware`` runs the hardware check and returns a
:class:`HardwareReport`. Authentication is required; the probe itself never
raises for missing hardware (a GPU-less host yields a CPU-only report).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...auth.base import Principal
from ...installer.hwcheck import check_hardware
from ..deps import get_current_principal
from ..registry import register_router
from ..schemas import HardwareReport

router = APIRouter(tags=["installer"])


@router.get("/hardware", response_model=HardwareReport)
def hardware(
    _: Annotated[Principal, Depends(get_current_principal)],
) -> HardwareReport:
    """Return the host hardware report (GPU/CPU/RAM/disk + sizing)."""
    return check_hardware()


register_router("/api/installer", router)
