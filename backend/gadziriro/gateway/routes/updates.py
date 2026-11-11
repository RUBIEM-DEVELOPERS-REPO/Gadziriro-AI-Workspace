"""Signed-update routes (FR-30) — admin only.

* ``POST /api/updates/apply`` — apply a base64-encoded signed bundle.
* ``POST /api/updates/rollback`` — revert to the previous version.
* ``GET /api/updates/history`` — current version + apply/rollback history.

Verification is offline against the verify key held by the shared
:class:`~gadziriro.updates.apply.UpdateManager` on ``app.state``.
"""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...auth.base import Principal, Role
from ...core.errors import GadziriroError
from ...updates.apply import UpdateManager
from ..deps import get_update_manager, require_role
from ..registry import register_router

router = APIRouter(tags=["updates"])

_require_admin = require_role(Role.ADMIN)


class ApplyUpdateIn(BaseModel):
    """Body for applying an update: the signed bundle, base64-encoded."""

    bundle_b64: str
    force: bool = False


@router.post("/apply")
def apply_update(
    body: ApplyUpdateIn,
    manager: Annotated[UpdateManager, Depends(get_update_manager)],
    _: Annotated[Principal, Depends(_require_admin)],
) -> dict[str, Any]:
    """Verify and apply a signed update bundle (400 if unsigned/tampered)."""
    try:
        bundle = base64.b64decode(body.bundle_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise GadziriroError("bundle_b64 is not valid base64") from exc
    version = manager.apply_update(bundle, force=body.force)
    return {"current_version": version}


@router.post("/rollback")
def rollback_update(
    manager: Annotated[UpdateManager, Depends(get_update_manager)],
    _: Annotated[Principal, Depends(_require_admin)],
) -> dict[str, Any]:
    """Revert to the previously applied version (400 if none)."""
    return {"current_version": manager.rollback()}


@router.get("/history")
def update_history(
    manager: Annotated[UpdateManager, Depends(get_update_manager)],
    _: Annotated[Principal, Depends(_require_admin)],
) -> dict[str, Any]:
    """Return the current version and the apply/rollback history."""
    return {"current_version": manager.current_version, "history": manager.history()}


register_router("/api/updates", router)
