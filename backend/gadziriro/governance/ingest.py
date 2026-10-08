"""Approved-source ingestion and labelling (FR-33, FR-08).

Data may enter the workspace **only** from an explicitly approved source
(FR-33), and every dataset is labelled with a :class:`SensitivityLabel` on the
way in (FR-08) so downstream policy (egress, retention, DSAR) has something to
reason about. Both guarantees live here, at the single ingestion door.
"""

from __future__ import annotations

from typing import Collection, Optional, Union

from ..audit.base import AuditEvent, AuditSink
from ..core.errors import PolicyDenied
from ..registry.base import DatasetVersion
from ..registry.store import ObjectStoreRegistry
from .labels import SensitivityLabel

__all__ = ["ingest_dataset"]


def _coerce_label(sensitivity: Union[SensitivityLabel, str]) -> SensitivityLabel:
    """Return a :class:`SensitivityLabel` from a label or its string value."""
    if isinstance(sensitivity, SensitivityLabel):
        return sensitivity
    return SensitivityLabel(sensitivity)


def ingest_dataset(
    registry: ObjectStoreRegistry,
    name: str,
    data: bytes,
    *,
    source: str,
    sensitivity: Union[SensitivityLabel, str],
    subjects: Collection[str] = (),
    approved_sources: Collection[str],
    audit: Optional[AuditSink] = None,
) -> DatasetVersion:
    """Ingest ``data`` as a new version of dataset ``name`` (FR-33 + FR-08).

    ``source`` must be a member of ``approved_sources`` (a collection of allowed
    source identifiers, e.g. ``{"s3://acme-approved", "nas://ward4", "upload"}``)
    or the ingest is denied and **nothing** is stored — data can only come from
    approved sources (FR-33). On acceptance the dataset is registered with its
    ``sensitivity`` label and ``subjects`` (labelled on the way in, FR-08).

    ``sensitivity`` may be a :class:`SensitivityLabel` or its string value.

    :raises PolicyDenied: if ``source`` is not in ``approved_sources``.
    """
    label = _coerce_label(sensitivity)
    subject_tuple = tuple(subjects)

    if source not in approved_sources:
        if audit is not None:
            audit.append(
                AuditEvent(
                    actor="system",
                    action="data.ingest.denied",
                    target=name,
                    reason=f"source not approved: {source}",
                    level="security",
                    meta={"source": source, "sensitivity": label.value},
                )
            )
        raise PolicyDenied(f"data source not approved: {source}")

    dv = registry.add_dataset(
        name,
        data,
        sensitivity=label,
        source=source,
        subjects=subject_tuple,
    )

    if audit is not None:
        audit.append(
            AuditEvent(
                actor="system",
                action="data.ingest",
                target=dv.ref,
                reason=f"ingested from approved source: {source}",
                meta={
                    "source": source,
                    "sensitivity": label.value,
                    "subjects": list(subject_tuple),
                },
            )
        )

    return dv
