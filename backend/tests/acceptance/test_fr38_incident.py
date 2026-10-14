"""FR-38 acceptance: incident response + breach-notification workflow.

An operator opens a (breach) incident, works it through its lifecycle, and
produces a breach report. The report must reconstruct the full timeline from the
tamper-evident audit log and must flag that legal review is required before any
regulator notification is sent (BRD Β§9).
"""

from __future__ import annotations

from pathlib import Path

from gadziriro.audit.log import AuditLog
from gadziriro.incident.response import IncidentService, build_breach_report


def test_fr38_incident_and_breach_report_workflow(tmp_path: Path) -> None:
    audit = AuditLog(path=tmp_path / "audit.jsonl")
    svc = IncidentService(audit=audit)

    # 1. Open a suspected-breach incident with affected subjects.
    inc = svc.open_incident(
        "exfiltration of patient export",
        "critical",
        breach=True,
        affected_subjects=("alice", "bob"),
    )

    # 2. Work it through the lifecycle, each step audited.
    svc.update_incident(inc.incident_id, status="investigating", note="isolating host")
    svc.update_incident(inc.incident_id, status="contained", note="access revoked")
    closed = svc.close_incident(inc.incident_id)
    assert closed.status == "closed"

    # 3. Audit chain is intact and holds every transition.
    verify = audit.verify()
    assert verify.ok is True
    assert verify.count == 4  # open + 2 updates + close

    # 4. Produce the breach report for the regulator workflow.
    report = build_breach_report(inc, audit)

    assert report["breach"] is True
    assert report["affected_subjects"] == ["alice", "bob"]
    assert [e["action"] for e in report["timeline"]] == [
        "incident.open",
        "incident.update",
        "incident.update",
        "incident.close",
    ]
    # No claim without counsel sign-off.
    assert report["legal_review_required"] is True
    assert "legal review" in report["legal_review_note"].lower()
