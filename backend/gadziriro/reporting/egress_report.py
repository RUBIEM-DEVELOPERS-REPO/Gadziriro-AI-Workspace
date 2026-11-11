"""\"What left this machine\" admin report (FR-25).

Reads the tamper-evident audit log (read-only) and summarises every transfer-relevant
event — export requests/approvals/denials and egress blocks — into an evidence report
(O1 / NFR-01: prove zero unapproved egress). It never modifies the audit log.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# Actions that represent data attempting to (or being allowed to) leave the box.
_APPROVED_ACTIONS = {"export.approve", "export.auto_approved", "transfer.approve"}
_DENIED_ACTIONS = {"export.deny", "egress.deny", "transfer.deny"}
_REQUEST_ACTIONS = {"export.request", "transfer.request"}
_RELEVANT = _APPROVED_ACTIONS | _DENIED_ACTIONS | _REQUEST_ACTIONS


@dataclass(frozen=True)
class EgressReport:
    generated_at: str
    entries: list[dict] = field(default_factory=list)
    total: int = 0
    approved_count: int = 0
    denied_count: int = 0


def _read_records(audit_log) -> list[dict]:
    path = getattr(audit_log, "path", None)
    if path is None:
        return []
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def build_egress_report(audit_log, *, since: Optional[str] = None) -> EgressReport:
    """Summarise transfer-relevant audit events into an egress evidence report."""
    entries: list[dict] = []
    approved = denied = 0
    for rec in _read_records(audit_log):
        action = rec.get("action", "")
        if action not in _RELEVANT:
            continue
        ts = rec.get("ts", "")
        if since is not None and ts and ts < since:
            continue
        is_approved = action in _APPROVED_ACTIONS
        is_denied = action in _DENIED_ACTIONS
        if is_approved:
            approved += 1
        if is_denied:
            denied += 1
        entries.append(
            {
                "ts": ts,
                "actor": rec.get("actor", ""),
                "action": action,
                "target": rec.get("target", ""),
                "approved": is_approved,
                "reason": rec.get("reason", ""),
            }
        )
    return EgressReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        entries=entries,
        total=len(entries),
        approved_count=approved,
        denied_count=denied,
    )


def render_text(report: EgressReport) -> str:
    """Render the egress report as a readable admin summary."""
    lines = [
        "# What left this machine",
        f"generated_at: {report.generated_at}",
        f"total transfer events: {report.total} "
        f"(approved: {report.approved_count}, denied/blocked: {report.denied_count})",
        "",
    ]
    for e in report.entries:
        status = "APPROVED" if e["approved"] else "blocked/other"
        lines.append(
            f"- {e['ts']} {e['actor']} {e['action']} {e['target']} "
            f"[{status}] {e['reason']}"
        )
    if not report.entries:
        lines.append("- (no transfer events recorded)")
    return "\n".join(lines)
