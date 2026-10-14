"""Data-subject access requests via lineage (FR-23).

A data subject can ask which models were built from their data and demand its
erasure. Model lineage (:class:`~gadziriro.registry.base.LineageRecord`) names
the exact dataset versions each model was trained on, and those versions record
the subjects they contain — so the registry can walk lineage back to a subject
and answer both questions without a separate index that could drift.

Phase 1 satisfies FR-23: *find* every affected model and *flag* it for
retraining/removal. Full export and erasure of the underlying data itself is
Phase 2 (FR-45).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ..audit.base import AuditEvent, AuditSink
from ..registry.base import ModelVersion
from ..registry.store import ObjectStoreRegistry

__all__ = ["find_subject_models", "erase_subject"]


def find_subject_models(
    registry: ObjectStoreRegistry, subject_id: str
) -> list[ModelVersion]:
    """Return every model built from a dataset containing ``subject_id`` (FR-23).

    Thin wrapper over
    :meth:`~gadziriro.registry.store.ObjectStoreRegistry.models_for_subject`,
    which resolves each model's lineage back to the exact dataset versions and
    checks their recorded subjects.
    """
    return registry.models_for_subject(subject_id)


def erase_subject(
    registry: ObjectStoreRegistry,
    subject_id: str,
    *,
    reason: str = "DSAR erasure",
    audit: Optional[AuditSink] = None,
) -> dict[str, Any]:
    """Flag every model built from ``subject_id``'s data for retraining (FR-23).

    Finds each affected model via lineage and flags it (``flagged=True``) with
    ``reason`` so it can be retrained or removed. Returns a report::

        {"subject_id": ..., "flagged": [<model refs>], "at": <iso timestamp>}

    (Erasure of the subject's data itself is Phase 2, FR-45; here we deliver the
    FR-23 guarantee: find the models and flag them.)
    """
    affected = find_subject_models(registry, subject_id)
    flagged_refs: list[str] = []
    for model in affected:
        updated = registry.flag_model(model.name, model.version, reason)
        flagged_refs.append(updated.ref)

    report: dict[str, Any] = {
        "subject_id": subject_id,
        "flagged": flagged_refs,
        "at": datetime.now(timezone.utc).isoformat(),
    }

    if audit is not None:
        audit.append(
            AuditEvent(
                actor="system",
                action="dsar.erase",
                target=subject_id,
                reason=reason,
                level="security",
                meta={"flagged": flagged_refs},
            )
        )

    return report
