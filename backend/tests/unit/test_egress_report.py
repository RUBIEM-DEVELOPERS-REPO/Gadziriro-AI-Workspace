"""Unit tests for the egress report."""

from __future__ import annotations

from gadziriro.audit.base import AuditEvent
from gadziriro.audit.log import AuditLog
from gadziriro.reporting.egress_report import build_egress_report, render_text


def _seed(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append(AuditEvent(actor="alice", action="export.request", target="model@1"))
    log.append(AuditEvent(actor="admin", action="export.approve", target="model@1"))
    log.append(AuditEvent(actor="bob", action="egress.deny", target="8.8.8.8"))
    log.append(AuditEvent(actor="sys", action="data.ingest", target="ds@1"))  # inbound
    log.append(AuditEvent(actor="alice", action="auth.login", target="alice"))
    return log


def test_report_selects_transfer_events(tmp_path) -> None:
    log = _seed(tmp_path)
    report = build_egress_report(log)
    actions = {e["action"] for e in report.entries}
    assert actions == {"export.request", "export.approve", "egress.deny"}
    assert report.total == 3
    assert report.approved_count == 1
    assert report.denied_count == 1


def test_render_text_lists_events(tmp_path) -> None:
    log = _seed(tmp_path)
    text = render_text(build_egress_report(log))
    assert "What left this machine" in text
    assert "export.approve" in text


def test_since_filter(tmp_path) -> None:
    log = _seed(tmp_path)
    # A future cutoff removes everything.
    report = build_egress_report(log, since="2999-01-01T00:00:00+00:00")
    assert report.total == 0
