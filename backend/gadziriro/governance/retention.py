"""Retention windows and scheduled deletion with proof (FR-22).

Each dataset can carry a :class:`RetentionPolicy` — a fixed number of retain
days, or an absolute cut-off date. :func:`apply_retention` is the scheduled job
that walks the registered dataset versions, deletes any that have aged out of
their window, and leaves behind a tamper-evident *deletion proof* for each one:
scheduled deletion with proof that it actually happened.

Because this package must not modify the registry, deletion is performed through
the **same** :class:`~gadziriro.core.objectstore.LocalObjectStore` the registry
persists into. The registry lays its blobs out under
``datasets/<name>/<version>/...``, so removing that version prefix from the store
removes the version. Callers therefore construct the registry with a store they
also hold and pass that store in here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..audit.base import AuditEvent, AuditSink
from ..core.canonical_json import canonical_bytes
from ..core.crypto import hash_record
from ..core.objectstore import ObjectStore
from ..registry.base import DatasetVersion
from ..registry.store import ObjectStoreRegistry

__all__ = ["RetentionPolicy", "apply_retention"]

_DATASETS = "datasets"
_PROOFS = "deletion_proofs"


@dataclass(frozen=True)
class RetentionPolicy:
    """How long a named dataset's versions may be retained (FR-22).

    Exactly one of ``retain_days`` (a relative window measured from each
    version's ``created_at``) or ``retain_until`` (an absolute ISO-8601 date or
    datetime cut-off) must be set.
    """

    dataset_name: str
    retain_days: Optional[int] = None
    retain_until: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.retain_days is None) == (self.retain_until is None):
            raise ValueError(
                "RetentionPolicy requires exactly one of retain_days or retain_until"
            )


def _as_utc(dt: datetime) -> datetime:
    """Return ``dt`` as a timezone-aware UTC datetime (assume UTC if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 date or datetime into an aware UTC datetime."""
    return _as_utc(datetime.fromisoformat(value))


def _is_expired(dv: DatasetVersion, policy: RetentionPolicy, now: datetime) -> bool:
    """Return True if ``dv`` has aged out of ``policy``'s window at ``now``."""
    created = _parse_iso(dv.created_at)
    if policy.retain_days is not None:
        return created + timedelta(days=policy.retain_days) < now
    assert policy.retain_until is not None  # guaranteed by __post_init__
    return now > _parse_iso(policy.retain_until)


def _version_prefix(name: str, version: int) -> str:
    """Return the object-store prefix holding ``name``@``version``'s blobs."""
    return f"{_DATASETS}/{name}/{version}"


def _proof_key(name: str, version: int) -> str:
    """Return the object-store key for ``name``@``version``'s deletion proof."""
    return f"{_PROOFS}/{name}/{version}.json"


def _make_proof(dv: DatasetVersion, now: datetime, reason: str) -> dict[str, Any]:
    """Build the tamper-evident deletion-proof record for ``dv``.

    The ``proof_hash`` covers every other field (via
    :func:`~gadziriro.core.crypto.hash_record`), so re-hashing the record with
    its ``proof_hash`` stripped must reproduce the stored value.
    """
    record: dict[str, Any] = {
        "dataset_ref": dv.ref,
        "deleted_at": now.isoformat(),
        "checksum_of_deleted": dv.checksum,
        "reason": reason,
    }
    record["proof_hash"] = hash_record(record)
    return record


def apply_retention(
    registry: ObjectStoreRegistry,
    store: ObjectStore,
    policies: list[RetentionPolicy],
    *,
    now: Optional[datetime] = None,
    audit: Optional[AuditSink] = None,
) -> list[dict[str, Any]]:
    """Run scheduled deletion for ``policies`` and return the deletion proofs.

    For every dataset version older than its policy's window at ``now`` (default:
    current UTC time): the version's blobs are deleted from ``store`` (the same
    object store the registry persists into) and a tamper-evident proof record is
    written under ``deletion_proofs/<name>/<version>.json``. The list of proof
    records (newest policy order) is returned.

    ``now`` is injectable so the scheduler — and tests — can drive the clock.
    """
    current = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    reason = "retention window elapsed"
    proofs: list[dict[str, Any]] = []

    for policy in policies:
        for dv in registry.list_dataset_versions(policy.dataset_name):
            if not _is_expired(dv, policy, current):
                continue

            store.delete(_version_prefix(dv.name, dv.version))
            proof = _make_proof(dv, current, reason)
            store.put(_proof_key(dv.name, dv.version), canonical_bytes(proof))
            proofs.append(proof)

            if audit is not None:
                audit.append(
                    AuditEvent(
                        actor="system",
                        action="data.retention.delete",
                        target=dv.ref,
                        reason=reason,
                        level="security",
                        meta={
                            "checksum_of_deleted": dv.checksum,
                            "proof_hash": proof["proof_hash"],
                        },
                    )
                )

    return proofs
