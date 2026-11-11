"""Data Protection Impact Assessment (DPIA) templates + workflow — FR-47.

An officer creates a DPIA (optionally from a starter template of common privacy
risks), fills in risks and mitigations, moves it draft -> in_review -> approved, and
exports it. This is an engineering workflow, not legal advice (BRD §9).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from ..core.canonical_json import canonical_json
from ..core.errors import GadziriroError, NotFound

_STATUSES = ("draft", "in_review", "approved")
_TRANSITIONS = {
    "draft": {"in_review"},
    "in_review": {"approved", "draft"},
    "approved": set(),
}


@dataclass
class DpiaRisk:
    description: str
    likelihood: str  # low | med | high
    impact: str  # low | med | high
    mitigation: str
    residual: str  # low | med | high


@dataclass
class Dpia:
    dpia_id: str
    title: str
    scope: str
    assessor: str
    status: str
    created_at: str
    updated_at: str
    risks: list[DpiaRisk] = field(default_factory=list)


DPIA_TEMPLATE: tuple[DpiaRisk, ...] = (
    DpiaRisk(
        "Re-identification of individuals",
        "med",
        "high",
        "Minimise + pseudonymise",
        "low",
    ),
    DpiaRisk(
        "Excessive data retention", "med", "med", "Per-dataset retention + purge", "low"
    ),
    DpiaRisk(
        "Cross-border transfer",
        "low",
        "high",
        "No egress by default; policy-gated",
        "low",
    ),
    DpiaRisk("Unauthorised access", "med", "high", "RBAC + MFA + audit", "low"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DpiaService:
    """In-memory DPIA store + lifecycle."""

    def __init__(self) -> None:
        self._dpias: dict[str, Dpia] = {}

    def create_dpia(
        self, title: str, scope: str, assessor: str, *, from_template: bool = True
    ) -> Dpia:
        did = f"dpia-{uuid.uuid4().hex[:8]}"
        now = _now()
        risks = [DpiaRisk(**asdict(r)) for r in DPIA_TEMPLATE] if from_template else []
        dpia = Dpia(
            dpia_id=did,
            title=title,
            scope=scope,
            assessor=assessor,
            status="draft",
            created_at=now,
            updated_at=now,
            risks=risks,
        )
        self._dpias[did] = dpia
        return dpia

    def add_risk(self, dpia_id: str, risk: DpiaRisk) -> Dpia:
        dpia = self.get(dpia_id)
        dpia.risks.append(risk)
        dpia.updated_at = _now()
        return dpia

    def set_status(self, dpia_id: str, status: str) -> Dpia:
        dpia = self.get(dpia_id)
        if status not in _STATUSES:
            raise GadziriroError(f"unknown DPIA status: {status}")
        if status != dpia.status and status not in _TRANSITIONS[dpia.status]:
            raise GadziriroError(f"invalid DPIA transition {dpia.status} -> {status}")
        dpia.status = status
        dpia.updated_at = _now()
        return dpia

    def get(self, dpia_id: str) -> Dpia:
        try:
            return self._dpias[dpia_id]
        except KeyError as exc:
            raise NotFound(f"unknown DPIA: {dpia_id}") from exc

    def list_dpias(self) -> list[Dpia]:
        return list(self._dpias.values())

    def export(self, dpia_id: str, out_store) -> str:
        dpia = self.get(dpia_id)
        payload = {
            "dpia_id": dpia.dpia_id,
            "title": dpia.title,
            "scope": dpia.scope,
            "assessor": dpia.assessor,
            "status": dpia.status,
            "created_at": dpia.created_at,
            "updated_at": dpia.updated_at,
            "risks": [asdict(r) for r in dpia.risks],
            "note": "Engineering artifact, not legal advice (BRD §9).",
        }
        key = f"dpia/{dpia.dpia_id}.json"
        out_store.put(key, (canonical_json(payload) + "\n").encode("utf-8"))
        return key
