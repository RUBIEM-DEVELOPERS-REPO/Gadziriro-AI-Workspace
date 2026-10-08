"""Audit contract. Implementations (log.py) must satisfy this Protocol.

Design (ported conceptually from Atomic's server/src/lib/audit.ts):
- append-only JSONL, one record per line
- each record carries `seq` (monotonic), `prev_hash`, `hash`
- hash = sha256(canonical_json(record without its own `hash`))
- first record's prev_hash == GENESIS
- verify() recomputes the whole chain and reports the first broken seq
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class AuditEvent:
    """What happened. Actor + action + context; never includes secrets or payloads."""

    actor: str  # authenticated principal, or "system"
    action: str  # e.g. "auth.login", "session.start", "export.request", "egress.deny"
    target: str = ""  # what was acted on (resource id, address, dataset)
    reason: str = ""  # why allowed/denied
    level: str = "info"  # info | warn | security
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    count: int
    broken_at: Optional[int] = None  # first seq where the chain is broken, if any
    detail: str = ""


@runtime_checkable
class AuditSink(Protocol):
    """Anything recording security-relevant events depends on this, not on log.py."""

    def append(self, event: AuditEvent) -> dict[str, Any]:
        """Append an event; return the written record (seq/hash). Raises AuditError."""
        ...

    def verify(self) -> VerifyResult:
        """Recompute the hash chain from genesis; report the first break if any."""
        ...
