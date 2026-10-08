"""CLI helper to verify the tamper-evident audit log (FR-19).

Thin wrapper over :meth:`gadziriro.audit.log.AuditLog.verify` that prints a
human-readable result and returns a process exit code.
"""

from __future__ import annotations

from pathlib import Path

from ..audit.log import AuditLog
from ..core.errors import AuditError


def verify_cmd(audit_dir: Path) -> int:
    """Verify ``<audit_dir>/audit.jsonl`` and return an exit code.

    :returns: ``0`` if the chain is intact, ``1`` otherwise (broken chain or an
        unreadable/corrupt log).
    """
    path = Path(audit_dir) / "audit.jsonl"
    try:
        log = AuditLog(path=path)
        result = log.verify()
    except AuditError as exc:
        print(f"audit: ERROR — {exc}")
        return 1
    if result.ok:
        print(f"audit: OK — {result.count} record(s), chain intact")
        return 0
    print(
        f"audit: BROKEN at seq {result.broken_at} "
        f"(verified {result.count} before break): {result.detail}"
    )
    return 1
