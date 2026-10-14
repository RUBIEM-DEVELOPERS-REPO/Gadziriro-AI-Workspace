"""Governance routes (FR-08, FR-22, FR-23, FR-33) — compliance/admin only.

Surfaces the governance seam over the injected registry + object store:

* ``POST /api/governance/ingest`` — approved-source ingest with a sensitivity
  label (FR-33 + FR-08).
* ``POST /api/governance/retention/run`` — run scheduled deletion with proof
  (FR-22).
* ``GET /api/governance/dsar/{subject_id}`` — find every model built from a
  subject's data (FR-23).
* ``POST /api/governance/dsar/{subject_id}/erase`` — flag those models for
  retraining/removal (FR-23).

All routes require :data:`Role.COMPLIANCE` *or* :data:`Role.ADMIN`.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ...audit.base import AuditSink
from ...auth.base import Principal, Role
from ...governance.dsar import erase_subject, find_subject_models
from ...governance.ingest import ingest_dataset
from ...governance.retention import RetentionPolicy, apply_retention
from ...registry.store import ObjectStoreRegistry
from ..deps import get_audit, get_object_store, get_registry, require_any_role
from ..registry import register_router

router = APIRouter(tags=["governance"])

_require_compliance = require_any_role(Role.COMPLIANCE, Role.ADMIN)


class IngestIn(BaseModel):
    """Body for an approved-source dataset ingest (FR-33 + FR-08)."""

    name: str
    content: str = ""
    source: str
    sensitivity: str
    subjects: list[str] = Field(default_factory=list)
    approved_sources: list[str] = Field(default_factory=list)


class RetentionPolicyIn(BaseModel):
    """One retention policy (exactly one of the two windows is set)."""

    dataset_name: str
    retain_days: Optional[int] = None
    retain_until: Optional[str] = None


class RetentionRunIn(BaseModel):
    """Body for running retention over a set of policies."""

    policies: list[RetentionPolicyIn] = Field(default_factory=list)


@router.post("/ingest")
def ingest(
    body: IngestIn,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    audit: Annotated[AuditSink, Depends(get_audit)],
    _: Annotated[Principal, Depends(_require_compliance)],
) -> dict[str, Any]:
    """Ingest a dataset from an approved source with a sensitivity label.

    :raises PolicyDenied: if the source is not approved (mapped to HTTP 403).
    """
    dv = ingest_dataset(
        registry,
        body.name,
        body.content.encode("utf-8"),
        source=body.source,
        sensitivity=body.sensitivity,
        subjects=tuple(body.subjects),
        approved_sources=tuple(body.approved_sources),
        audit=audit,
    )
    return {
        "name": dv.name,
        "version": dv.version,
        "ref": dv.ref,
        "sensitivity": dv.sensitivity.value,
        "source": dv.source,
        "checksum": dv.checksum,
        "subjects": list(dv.subjects),
    }


@router.post("/retention/run")
def run_retention(
    body: RetentionRunIn,
    request: Request,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    audit: Annotated[AuditSink, Depends(get_audit)],
    _: Annotated[Principal, Depends(_require_compliance)],
) -> dict[str, Any]:
    """Run scheduled deletion for the given policies and return the proofs."""
    store = get_object_store(request)
    policies = [
        RetentionPolicy(
            dataset_name=p.dataset_name,
            retain_days=p.retain_days,
            retain_until=p.retain_until,
        )
        for p in body.policies
    ]
    proofs = apply_retention(registry, store, policies, audit=audit)
    return {"deleted": len(proofs), "proofs": proofs}


@router.get("/dsar/{subject_id}")
def dsar_find(
    subject_id: str,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    _: Annotated[Principal, Depends(_require_compliance)],
) -> dict[str, Any]:
    """Return every model built from ``subject_id``'s data (FR-23)."""
    models = find_subject_models(registry, subject_id)
    return {
        "subject_id": subject_id,
        "models": [
            {"ref": m.ref, "name": m.name, "version": m.version, "flagged": m.flagged}
            for m in models
        ],
    }


@router.post("/dsar/{subject_id}/erase")
def dsar_erase(
    subject_id: str,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    audit: Annotated[AuditSink, Depends(get_audit)],
    _: Annotated[Principal, Depends(_require_compliance)],
) -> dict[str, Any]:
    """Flag every model built from ``subject_id``'s data for removal (FR-23)."""
    return erase_subject(registry, subject_id, audit=audit)


register_router("/api/governance", router)
