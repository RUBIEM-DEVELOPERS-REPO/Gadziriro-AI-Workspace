"""Support-bundle routes (FR-40) — admin only.

``POST /api/support/bundle`` builds a PII-stripped troubleshooting bundle from the
workspace data directory, writes it into the shared object store, and returns the
bundle key plus the count of redacted fields. Restricted to :data:`Role.ADMIN`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from ...auth.base import Principal, Role
from ...ops.support_bundle import build_support_bundle
from ..deps import get_object_store, require_role
from ..registry import register_router

router = APIRouter(tags=["support"])


@router.post("/bundle")
def build_bundle(
    request: Request,
    store: Annotated[Any, Depends(get_object_store)],
    _: Annotated[Principal, Depends(require_role(Role.ADMIN))],
) -> dict[str, Any]:
    """Build a PII-stripped support bundle and store it (FR-40)."""
    settings = request.app.state.settings
    return build_support_bundle(data_dir=settings.data_dir, out_store=store)


register_router("/api/support", router)
