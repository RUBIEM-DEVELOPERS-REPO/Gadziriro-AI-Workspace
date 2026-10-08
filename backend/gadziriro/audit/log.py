"""Tamper-evident audit log — concrete :class:`AuditSink` (FR-19, NFR-04).

An append-only, hash-chained JSONL file. Each line is one record:

    {seq, ts, actor, action, target, reason, level, meta, prev_hash, hash}

``hash`` is ``sha256_hex(canonical_bytes(record_without_hash))`` using the shared
canonical-JSON helpers, so every component hashes records byte-for-byte the same
way. The first record's ``prev_hash`` is :data:`GENESIS`; each later record's
``prev_hash`` is the previous record's ``hash``. Any edit, deletion, or reorder
of a past record breaks the chain and is reported by :meth:`AuditLog.verify`.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..core.canonical_json import canonical_json
from ..core.config import Settings, load_settings
from ..core.crypto import GENESIS, hash_record
from ..core.errors import AuditError
from .base import AuditEvent, VerifyResult

# Fields that make up a record, excluding the self-referential ``hash``.
_HASHED_FIELDS = (
    "seq",
    "ts",
    "actor",
    "action",
    "target",
    "reason",
    "level",
    "meta",
    "prev_hash",
)


def _now_iso() -> str:
    """Return the current time as an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class AuditLog:
    """Append-only, hash-chained audit log backed by a single JSONL file.

    Implements the :class:`gadziriro.audit.base.AuditSink` protocol.
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        *,
        settings: Optional[Settings] = None,
    ) -> None:
        """Open (or create) the audit log and recover its chain state.

        :param path: explicit JSONL path; defaults to
            ``settings.audit_dir / "audit.jsonl"``.
        :param settings: settings to derive the default path from; defaults to
            :func:`gadziriro.core.config.load_settings`.
        """
        if path is None:
            settings = settings or load_settings()
            settings.ensure_dirs()
            path = settings.audit_dir / "audit.jsonl"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_seq = 0
        self._last_hash = GENESIS
        self.recover()

    # -- chain state -----------------------------------------------------

    def recover(self) -> None:
        """Resume ``seq`` and ``prev_hash`` from the file tail.

        Empty or missing file resets to genesis. A corrupt tail (unparseable
        last line, or one missing ``seq``/``hash``) raises :class:`AuditError`.
        """
        if not self.path.exists():
            self._last_seq = 0
            self._last_hash = GENESIS
            return
        last_line = ""
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped:
                        last_line = stripped
        except OSError as exc:  # pragma: no cover - filesystem failure
            raise AuditError(f"cannot read audit log {self.path}: {exc}") from exc
        if not last_line:
            self._last_seq = 0
            self._last_hash = GENESIS
            return
        try:
            record = json.loads(last_line)
            seq = int(record["seq"])
            last_hash = str(record["hash"])
        except (ValueError, KeyError, TypeError) as exc:
            raise AuditError(f"corrupt tail in audit log {self.path}: {exc}") from exc
        self._last_seq = seq
        self._last_hash = last_hash

    # -- write path ------------------------------------------------------

    def append(self, event: AuditEvent) -> dict[str, Any]:
        """Append ``event`` as the next chained record and return it.

        Durability: the line is flushed and ``fsync``-ed before returning.
        Any failure raises :class:`AuditError`.
        """
        record: dict[str, Any] = {
            "seq": self._last_seq + 1,
            "ts": _now_iso(),
            "actor": event.actor,
            "action": event.action,
            "target": event.target,
            "reason": event.reason,
            "level": event.level,
            "meta": dict(event.meta),
            "prev_hash": self._last_hash,
        }
        record["hash"] = hash_record({k: record[k] for k in _HASHED_FIELDS})
        line = canonical_json(record) + "\n"
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            raise AuditError(
                f"failed to append to audit log {self.path}: {exc}"
            ) from exc
        self._last_seq = record["seq"]
        self._last_hash = record["hash"]
        return record

    # -- verify path -----------------------------------------------------

    def verify(self) -> VerifyResult:
        """Recompute the whole chain from genesis and report the first break.

        Checks, per record: the stored ``hash`` matches a recomputed hash, the
        ``seq`` is monotonic (1, 2, 3, …), and ``prev_hash`` links to the prior
        record (:data:`GENESIS` for the first). ``broken_at`` is the 1-based
        position where the chain first fails.
        """
        if not self.path.exists():
            return VerifyResult(ok=True, count=0)

        try:
            with self.path.open("r", encoding="utf-8") as fh:
                lines = [ln for ln in (line.strip() for line in fh) if ln]
        except OSError as exc:  # pragma: no cover - filesystem failure
            raise AuditError(f"cannot read audit log {self.path}: {exc}") from exc

        expected_prev = GENESIS
        verified = 0
        for index, raw in enumerate(lines):
            position = index + 1  # 1-based expected seq for this line
            try:
                record = json.loads(raw)
            except ValueError:
                return VerifyResult(
                    ok=False,
                    count=verified,
                    broken_at=position,
                    detail=f"line {position} is not valid JSON",
                )
            if not isinstance(record, dict) or "hash" not in record:
                return VerifyResult(
                    ok=False,
                    count=verified,
                    broken_at=position,
                    detail=f"line {position} is not a valid record",
                )

            stored_hash = record["hash"]
            try:
                recomputed = hash_record({k: record[k] for k in _HASHED_FIELDS})
            except KeyError:
                return VerifyResult(
                    ok=False,
                    count=verified,
                    broken_at=position,
                    detail=f"line {position} is missing required fields",
                )
            if recomputed != stored_hash:
                return VerifyResult(
                    ok=False,
                    count=verified,
                    broken_at=position,
                    detail=f"hash mismatch at seq {position}",
                )
            if record.get("seq") != position:
                return VerifyResult(
                    ok=False,
                    count=verified,
                    broken_at=position,
                    detail=(
                        f"seq out of order: expected {position}, "
                        f"got {record.get('seq')}"
                    ),
                )
            if record.get("prev_hash") != expected_prev:
                return VerifyResult(
                    ok=False,
                    count=verified,
                    broken_at=position,
                    detail=f"broken linkage at seq {position}",
                )

            expected_prev = stored_hash
            verified += 1

        return VerifyResult(ok=True, count=verified)
