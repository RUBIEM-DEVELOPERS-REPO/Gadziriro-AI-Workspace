"""Incident response and breach-notification reporting (FR-38).

A security *incident* is tracked through an explicit lifecycle
(``open -> investigating -> contained -> closed``) and every transition is
written to the tamper-evident :class:`~gadziriro.audit.base.AuditSink`, so the
incident timeline itself is auditable (BRD Β§9).

:func:`build_breach_report` assembles a regulator-facing breach-notification
report from an :class:`Incident` plus the relevant audit events (who / what /
when, affected subjects, a chronological timeline). It is a *draft*: it carries
an explicit note that legal review / counsel sign-off is required before any
notification is sent, because no breach claim is made without that review
(BRD Β§9).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..audit.base import AuditEvent, AuditSink
from ..audit.log import AuditLog
from ..core.errors import NotFound

__all__ = ["Incident", "IncidentService", "build_breach_report"]

# Allowed incident lifecycle states, least-to-most resolved.
STATUSES: tuple[str, ...] = ("open", "investigating", "contained", "closed")

_LEGAL_REVIEW_NOTE = (
    "DRAFT - legal review / counsel sign-off is required before any breach "
    "notification is issued; no breach is claimed or reported without that "
    "review (BRD Β§9)."
)


def _now_iso() -> str:
    """Return the current time as an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Incident:
    """A tracked security incident and its current state.

    Attributes:
        incident_id: Unique identifier (assigned on open).
        title: Short human-readable summary.
        severity: Caller-defined severity (e.g. ``"low"``/``"high"``/``"critical"``).
        status: One of :data:`STATUSES`.
        opened_at: ISO-8601 UTC timestamp the incident was opened.
        updated_at: ISO-8601 UTC timestamp of the last transition.
        notes: Chronological investigation notes.
        breach: Whether this incident is (suspected to be) a personal-data breach.
        affected_subjects: Data-subject ids believed to be affected.
    """

    incident_id: str
    title: str
    severity: str
    status: str
    opened_at: str
    updated_at: str
    notes: list[str] = field(default_factory=list)
    breach: bool = False
    affected_subjects: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready copy of this incident."""
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "severity": self.severity,
            "status": self.status,
            "opened_at": self.opened_at,
            "updated_at": self.updated_at,
            "notes": list(self.notes),
            "breach": self.breach,
            "affected_subjects": list(self.affected_subjects),
        }


class IncidentService:
    """Open, update, and close security incidents, auditing every transition.

    Every lifecycle change is appended to the injected
    :class:`~gadziriro.audit.base.AuditSink` (if any) as an ``incident.open`` /
    ``incident.update`` / ``incident.close`` event, so the incident history is
    tamper-evident alongside the rest of the audit trail (FR-38, FR-19).
    """

    def __init__(self, audit: Optional[AuditSink] = None) -> None:
        """Create an incident service, optionally wired to an audit sink."""
        self._audit = audit
        self._incidents: dict[str, Incident] = {}

    # -- audit helper --------------------------------------------------------

    def _emit(
        self,
        action: str,
        incident: Incident,
        *,
        reason: str = "",
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Append an incident lifecycle event to the audit sink, if configured."""
        if self._audit is None:
            return
        event_meta: dict[str, Any] = {
            "incident_id": incident.incident_id,
            "status": incident.status,
            "severity": incident.severity,
            "breach": incident.breach,
        }
        if meta:
            event_meta.update(meta)
        self._audit.append(
            AuditEvent(
                actor="system",
                action=action,
                target=incident.incident_id,
                reason=reason or incident.title,
                level="security",
                meta=event_meta,
            )
        )

    # -- lifecycle -----------------------------------------------------------

    def open_incident(
        self,
        title: str,
        severity: str,
        *,
        breach: bool = False,
        affected_subjects: tuple[str, ...] = (),
    ) -> Incident:
        """Open a new incident in the ``open`` state and audit it (FR-38)."""
        now = _now_iso()
        incident = Incident(
            incident_id=uuid.uuid4().hex,
            title=title,
            severity=severity,
            status="open",
            opened_at=now,
            updated_at=now,
            notes=[],
            breach=breach,
            affected_subjects=list(affected_subjects),
        )
        self._incidents[incident.incident_id] = incident
        self._emit("incident.open", incident, reason=title)
        return incident

    def get_incident(self, incident_id: str) -> Incident:
        """Return the incident with ``incident_id`` or raise :class:`NotFound`."""
        try:
            return self._incidents[incident_id]
        except KeyError as exc:
            raise NotFound(f"incident not found: {incident_id}") from exc

    def update_incident(
        self,
        incident_id: str,
        *,
        status: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Incident:
        """Change an incident's status and/or append a note, auditing the change.

        Args:
            incident_id: The incident to update.
            status: New lifecycle status (must be one of :data:`STATUSES`).
            note: Investigation note to append.

        Raises:
            NotFound: if ``incident_id`` is unknown.
            ValueError: if ``status`` is not a recognised lifecycle state.
        """
        incident = self.get_incident(incident_id)
        if status is not None and status not in STATUSES:
            raise ValueError(f"unknown incident status: {status!r}")

        meta: dict[str, Any] = {}
        if note is not None:
            incident.notes.append(note)
            meta["note"] = note
        if status is not None:
            meta["from_status"] = incident.status
            incident.status = status
        incident.updated_at = _now_iso()
        self._emit("incident.update", incident, meta=meta)
        return incident

    def close_incident(self, incident_id: str) -> Incident:
        """Transition an incident to ``closed`` and audit it (FR-38)."""
        incident = self.get_incident(incident_id)
        meta = {"from_status": incident.status}
        incident.status = "closed"
        incident.updated_at = _now_iso()
        self._emit("incident.close", incident, meta=meta)
        return incident

    def list_incidents(self) -> list[Incident]:
        """Return all tracked incidents, oldest first (by ``opened_at``)."""
        return sorted(self._incidents.values(), key=lambda i: i.opened_at)


def _read_audit_events(audit_log: AuditLog) -> list[dict[str, Any]]:
    """Read every persisted audit record back from the log's JSONL file.

    The :class:`~gadziriro.audit.log.AuditLog` persists one JSON record per line;
    we read that file (never mutating it) to reconstruct the incident timeline.
    """
    path = Path(audit_log.path)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(json.loads(stripped))
            except ValueError:
                continue
    return events


def build_breach_report(incident: Incident, audit_log: AuditLog) -> dict[str, Any]:
    """Assemble a draft breach-notification report from an incident + audit trail.

    Pulls every audit record that references the incident (by ``target`` or
    ``meta.incident_id``) or one of its affected subjects, orders them into a
    chronological timeline (who / what / when), and packages the incident
    summary and affected subjects for the regulator-notification workflow.

    The report is explicitly a **draft**: ``legal_review_required`` is ``True``
    and ``legal_review_note`` carries the BRD Β§9 requirement that counsel sign
    off before any notification is sent.

    Args:
        incident: The incident to report on.
        audit_log: The audit log to reconstruct the timeline from (read-only).

    Returns:
        A JSON-ready report dict.
    """
    subjects = set(incident.affected_subjects)
    timeline: list[dict[str, Any]] = []
    for record in _read_audit_events(audit_log):
        meta = record.get("meta", {}) or {}
        touches_incident = (
            record.get("target") == incident.incident_id
            or meta.get("incident_id") == incident.incident_id
        )
        touches_subject = record.get("target") in subjects
        if not (touches_incident or touches_subject):
            continue
        timeline.append(
            {
                "seq": record.get("seq"),
                "ts": record.get("ts"),
                "actor": record.get("actor"),
                "action": record.get("action"),
                "target": record.get("target"),
                "reason": record.get("reason"),
                "level": record.get("level"),
            }
        )
    timeline.sort(key=lambda e: (e.get("seq") or 0))

    return {
        "incident": incident.to_dict(),
        "breach": incident.breach,
        "affected_subjects": list(incident.affected_subjects),
        "affected_subject_count": len(incident.affected_subjects),
        "timeline": timeline,
        "generated_at": _now_iso(),
        "legal_review_required": True,
        "legal_review_note": _LEGAL_REVIEW_NOTE,
    }
