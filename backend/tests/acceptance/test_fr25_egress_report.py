"""FR-25 acceptance: admin report of everything that left the machine."""

from __future__ import annotations

from gadziriro.audit.base import AuditEvent
from gadziriro.audit.log import AuditLog
from gadziriro.reporting.egress_report import build_egress_report


def test_egress_evidence_from_audit(tmp_path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    # An approved export and a blocked egress attempt, both recorded.
    log.append(AuditEvent(actor="admin", action="export.approve", target="weights@3"))
    log.append(
        AuditEvent(actor="user", action="egress.deny", target="api.evil.example")
    )

    report = build_egress_report(log)
    assert report.approved_count == 1
    assert report.denied_count == 1
    # The report is built from the tamper-evident chain, which still verifies.
    assert log.verify().ok
