"""DSAR routes (FR-45) — compliance / admin only.

Extends the Phase 1 find+flag path with the right of access and the right to
erasure over the shared registry + object store:

* ``POST /api/dsar/{subject}/export`` — export the subject's data into the shared
  object store under ``dsar_exports/<subject>/...`` and return the manifest.
* ``POST /api/dsar/{subject}/erase`` — erase the subject's data, flag every
  affected model, and record a tamper-evident deletion proof.

Every route requires :data:`Role.COMPLIANCE` or :data:`Role.ADMIN`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...audit.base import AuditSink
from ...auth.base import Principal, Role
from ...governance.dsar_export import erase_subject_data, export_subject_data
from ...registry.store import ObjectStoreRegistry
from ..deps import get_audit, get_object_store, get_registry, require_any_role
from ..registry import register_router

router = APIRouter(tags=["dsar"])

_require_compliance = require_any_role(Role.COMPLIANCE, Role.ADMIN)


class EraseIn(BaseModel):
    """Body for an erasure request (optional reason)."""

    reason: str = "DSAR erasure"


@router.post("/{subject}/export")
def export_subject(
    subject: str,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    store: Annotated[Any, Depends(get_object_store)],
    audit: Annotated[AuditSink, Depends(get_audit)],
    _: Annotated[Principal, Depends(_require_compliance)],
) -> dict[str, Any]:
    """Export every dataset containing ``subject`` plus its models (FR-45)."""
    return export_subject_data(registry, store, subject, out_store=store, audit=audit)


@router.post("/{subject}/erase")
def erase_subject(
    subject: str,
    body: EraseIn,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    store: Annotated[Any, Depends(get_object_store)],
    audit: Annotated[AuditSink, Depends(get_audit)],
    _: Annotated[Principal, Depends(_require_compliance)],
) -> dict[str, Any]:
    """Erase ``subject``'s data and flag every model built on it (FR-45)."""
    return erase_subject_data(registry, store, subject, reason=body.reason, audit=audit)


register_router("/api/dsar", router)
