"""Licensing routes (FR-48) — licence facts + use/export gates.

``GET /api/licensing/{model}`` returns the resolved licence record for a model
family; ``POST /api/licensing/check`` gates an intended use (and, when a
destination is given, an export) against the licence and export-control rules —
a blocked action raises :class:`PolicyDenied`, mapped to HTTP 403. Every route
requires an authenticated principal.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...auth.base import Principal
from ...licensing.checks import check_export_control, check_licence, licence_for
from ..deps import get_current_principal
from ..registry import register_router

router = APIRouter(tags=["licensing"])


class LicenceCheckIn(BaseModel):
    """Body for a licence / export-control check."""

    model: str
    intended_use: str = "commercial"
    destination: Optional[str] = None


@router.get("/{model}")
def get_licence(
    model: str,
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Return the licence record for ``model`` by family prefix (FR-48)."""
    return licence_for(model)


@router.post("/check")
def check(
    body: LicenceCheckIn,
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Gate a model's use (and export) against its licence (FR-48).

    :raises PolicyDenied: if the use or export is forbidden (HTTP 403).
    """
    check_licence(body.model, intended_use=body.intended_use)
    if body.destination is not None:
        check_export_control(body.model, destination=body.destination)
    return {"ok": True, "licence": licence_for(body.model)}


register_router("/api/licensing", router)
