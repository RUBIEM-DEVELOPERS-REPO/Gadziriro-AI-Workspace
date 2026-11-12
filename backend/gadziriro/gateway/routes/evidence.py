"""Auditor evidence-pack routes (FR-26) — admin or compliance.

* ``POST /api/evidence/export`` — build + store a single evidence pack.
* ``GET  /api/evidence`` — list prior packs.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...auth.base import Principal, Role
from ...compliance.evidence import build_evidence_pack
from ..deps import (
    get_audit,
    get_backup_service,
    get_object_store,
    get_registry,
    require_any_role,
)
from ..registry import register_router

router = APIRouter(tags=["evidence"])

_require_compliance_or_admin = require_any_role(Role.COMPLIANCE, Role.ADMIN)


class EvidenceExportIn(BaseModel):
    """Which compliance packs are active for this evidence export."""

    enabled_packs: list[str] = Field(default_factory=list)


@router.post("/export")
def export_evidence(
    body: EvidenceExportIn,
    audit: Annotated[Any, Depends(get_audit)],
    registry: Annotated[Any, Depends(get_registry)],
    store: Annotated[Any, Depends(get_object_store)],
    backup: Annotated[Any, Depends(get_backup_service)],
    _: Annotated[Principal, Depends(_require_compliance_or_admin)],
) -> dict[str, Any]:
    """Assemble and store an auditor evidence pack; return its manifest."""
    return build_evidence_pack(
        audit_log=audit,
        registry=registry,
        object_store=store,
        enabled_packs=tuple(body.enabled_packs),
        out_store=store,
        backup_service=backup,
    )


@router.get("")
def list_evidence(
    store: Annotated[Any, Depends(get_object_store)],
    _: Annotated[Principal, Depends(_require_compliance_or_admin)],
) -> list[dict[str, Any]]:
    """List prior evidence packs (newest first)."""
    out: list[dict[str, Any]] = []
    for key in store.list("evidence"):
        if not key.endswith(".json"):
            continue
        try:
            pack = json.loads(store.get(key).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        audit_section = pack.get("audit", {})
        out.append(
            {
                "pack_key": key,
                "generated_at": pack.get("generated_at", ""),
                "audit_ok": bool(audit_section.get("ok", False)),
                "sections": pack.get("sections", list(pack.keys())),
            }
        )
    out.sort(key=lambda p: p.get("generated_at", ""), reverse=True)
    return out


register_router("/api/evidence", router)
