"""Unit tests for incident response + breach reporting (FR-38)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gadziriro.audit.log import AuditLog
from gadziriro.core.errors import NotFound
from gadziriro.incident.response import Incident, IncidentService, build_breach_report


def _audit(tmp_path: Path) -> AuditLog:
    return AuditLog(path=tmp_path / "audit.jsonl")


def test_lifecycle_transitions_are_all_audited(tmp_path: Path) -> None:
    audit = _audit(tmp_path)
    svc = IncidentService(audit=audit)

    inc = svc.open_incident("laptop lost", "high")
    assert isinstance(inc, Incident)
    assert inc.status == "open"

    svc.update_incident(inc.incident_id, status="investigating", note="triaging")
    svc.update_incident(inc.incident_id, status="contained", note="disk encrypted")
    closed = svc.close_incident(inc.incident_id)

    assert closed.status == "closed"
    assert closed.notes == ["triaging", "disk encrypted"]

    # Each transition produced an audit record: open + 2 updates + close.
    actions = [e["action"] for e in _read_actions(audit)]
    assert actions == [
        "incident.open",
        "incident.update",
        "incident.update",
        "incident.close",
    ]
    assert audit.verify().ok is True


def test_get_unknown_incident_raises_not_found(tmp_path: Path) -> None:
    svc = IncidentService(audit=_audit(tmp_path))
    with pytest.raises(NotFound):
        svc.get_incident("does-not-exist")
    with pytest.raises(NotFound):
        svc.update_incident("does-not-exist", status="closed")


def test_invalid_status_rejected(tmp_path: Path) -> None:
    svc = IncidentService(audit=_audit(tmp_path))
    inc = svc.open_incident("x", "low")
    with pytest.raises(ValueError):
        svc.update_incident(inc.incident_id, status="banana")


def test_list_incidents_returns_all(tmp_path: Path) -> None:
    svc = IncidentService(audit=_audit(tmp_path))
    a = svc.open_incident("a", "low")
    b = svc.open_incident("b", "low")
    ids = {i.incident_id for i in svc.list_incidents()}
    assert ids == {a.incident_id, b.incident_id}


def test_breach_report_pulls_timeline_and_marks_legal_review(tmp_path: Path) -> None:
    audit = _audit(tmp_path)
    svc = IncidentService(audit=audit)

    inc = svc.open_incident(
        "db exfiltration",
        "critical",
        breach=True,
        affected_subjects=("alice", "bob"),
    )
    svc.update_incident(inc.incident_id, status="investigating", note="scoping")
    svc.close_incident(inc.incident_id)

    report = build_breach_report(inc, audit)

    assert report["breach"] is True
    assert report["affected_subjects"] == ["alice", "bob"]
    assert report["affected_subject_count"] == 2
    assert report["legal_review_required"] is True
    assert "legal review" in report["legal_review_note"].lower()
    assert "generated_at" in report

    # The timeline is assembled from the audit log, in chain order.
    timeline_actions = [e["action"] for e in report["timeline"]]
    assert timeline_actions == [
        "incident.open",
        "incident.update",
        "incident.close",
    ]
    seqs = [e["seq"] for e in report["timeline"]]
    assert seqs == sorted(seqs)


def test_service_without_audit_still_works() -> None:
    svc = IncidentService()
    inc = svc.open_incident("no audit", "low")
    svc.update_incident(inc.incident_id, status="closed")
    assert svc.get_incident(inc.incident_id).status == "closed"


def _read_actions(audit: AuditLog) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(audit.path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
