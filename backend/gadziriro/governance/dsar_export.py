"""DSAR data export & erasure (FR-45) — extends the FR-23 find+flag path.

Phase 1 (:mod:`gadziriro.governance.dsar`) answers *which* models were built from
a subject's data and *flags* them. FR-45 goes further: it exports a copy of the
subject's actual data (the "right of access") and erases that data from the
object store (the "right to erasure"), flagging every affected model for
retrain/removal and leaving a tamper-evident deletion proof behind.

Dataset discovery
-----------------
The registry does not expose a public "list all dataset names" call, so we
enumerate names directly from the object store's key layout, which the registry
documents as::

    datasets/<name>/<version>/blob        # raw dataset bytes
    datasets/<name>/<version>/meta.json   # DatasetVersion metadata

We scan keys under the ``datasets/`` prefix, take the ``<name>`` segment, and
then use :meth:`ObjectStoreRegistry.list_dataset_versions` for the authoritative
metadata (sensitivity, subjects, checksum). This never duplicates the registry's
own metadata parsing — it only recovers the set of names to feed back into it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from ..audit.base import AuditEvent, AuditSink
from ..core.canonical_json import canonical_json
from ..core.crypto import sha256_hex
from ..core.errors import NotFound
from ..core.objectstore import ObjectStore
from ..registry.store import ObjectStoreRegistry

__all__ = ["export_subject_data", "erase_subject_data"]

_DATASETS = "datasets"
_EXPORT_PREFIX = "dsar_exports"
_DELETION_PREFIX = "dsar_deletions"


def _now_iso() -> str:
    """Return the current time as an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _blob_key(name: str, version: int) -> str:
    """Return the object-store key for a dataset blob (registry key layout)."""
    return f"{_DATASETS}/{name}/{version}/blob"


def _dataset_names(store: ObjectStore) -> list[str]:
    """Return the distinct dataset names present in ``store`` (``datasets/<name>/``).

    Derived from the documented registry key layout; see the module docstring.
    """
    prefix = f"{_DATASETS}/"
    names: set[str] = set()
    for key in store.list(prefix):
        rest = key[len(prefix) :]
        parts = rest.split("/")
        if len(parts) >= 2 and parts[0]:
            names.add(parts[0])
    return sorted(names)


def _subject_dataset_versions(
    registry: ObjectStoreRegistry, store: ObjectStore, subject_id: str
) -> list[Any]:
    """Return every :class:`DatasetVersion` whose ``subjects`` lists ``subject_id``."""
    matches: list[Any] = []
    for name in _dataset_names(store):
        for dv in registry.list_dataset_versions(name):
            if subject_id in dv.subjects:
                matches.append(dv)
    return matches


def export_subject_data(
    registry: ObjectStoreRegistry,
    store: ObjectStore,
    subject_id: str,
    *,
    out_store: ObjectStore,
    audit: Optional[AuditSink] = None,
) -> dict[str, Any]:
    """Export every dataset containing ``subject_id`` plus the models built on it.

    Gathers each :class:`DatasetVersion` whose ``subjects`` includes
    ``subject_id``, copies the subject's dataset blobs into ``out_store`` under
    ``dsar_exports/<subject_id>/datasets/<ref>.blob``, writes a JSON manifest
    alongside them, and returns that manifest. Models are resolved via
    :meth:`ObjectStoreRegistry.models_for_subject` (lineage), not copied.

    Args:
        registry: Registry to read dataset/model metadata from.
        store: Source object store holding the dataset blobs.
        subject_id: The data subject to export.
        out_store: Destination object store for the export package.
        audit: Optional audit sink; a ``dsar.export`` event is appended if given.

    Returns:
        ``{"subject_id", "datasets": [refs], "models": [refs], "exported_at",
        "package_key"}``.
    """
    exported_at = _now_iso()
    versions = _subject_dataset_versions(registry, store, subject_id)

    dataset_entries: list[dict[str, Any]] = []
    for dv in versions:
        blob_key = _blob_key(dv.name, dv.version)
        safe_ref = dv.ref.replace("/", "_")
        package_blob = f"{_EXPORT_PREFIX}/{subject_id}/datasets/{safe_ref}.blob"
        try:
            data = store.get(blob_key)
        except NotFound:
            data = b""
        out_store.put(package_blob, data)
        dataset_entries.append(
            {
                "ref": dv.ref,
                "sensitivity": dv.sensitivity.value,
                "checksum": dv.checksum,
                "blob_key": package_blob,
            }
        )

    models = registry.models_for_subject(subject_id)
    manifest: dict[str, Any] = {
        "subject_id": subject_id,
        "datasets": [e["ref"] for e in dataset_entries],
        "dataset_entries": dataset_entries,
        "models": [m.ref for m in models],
        "exported_at": exported_at,
    }
    package_key = f"{_EXPORT_PREFIX}/{subject_id}/manifest.json"
    out_store.put(package_key, canonical_json(manifest).encode("utf-8"))
    manifest["package_key"] = package_key

    if audit is not None:
        audit.append(
            AuditEvent(
                actor="system",
                action="dsar.export",
                target=subject_id,
                reason="DSAR subject-data export (FR-45)",
                level="security",
                meta={
                    "datasets": manifest["datasets"],
                    "models": manifest["models"],
                    "package_key": package_key,
                },
            )
        )

    return manifest


def erase_subject_data(
    registry: ObjectStoreRegistry,
    store: ObjectStore,
    subject_id: str,
    *,
    reason: str = "DSAR erasure",
    audit: Optional[AuditSink] = None,
) -> dict[str, Any]:
    """Erase ``subject_id``'s dataset data and flag every model built on it (FR-45).

    For each dataset version listing the subject this: records the version ref +
    checksum as deletion proof, deletes the raw blob from ``store``, and redacts
    the subject out of the stored metadata (marking it redacted). It then flags
    every affected model (:meth:`ObjectStoreRegistry.flag_model`) for
    retrain/removal, writes a tamper-evident deletion-proof record into ``store``
    under ``dsar_deletions/<subject_id>/...``, and returns a summary.

    Args:
        registry: Registry to read/flag dataset & model metadata.
        store: Object store holding the dataset blobs/metadata to erase.
        subject_id: The data subject to erase.
        reason: Reason recorded on the flag, proof, and audit event.
        audit: Optional audit sink; a ``dsar.erase`` event is appended if given.

    Returns:
        ``{"subject_id", "erased": [refs], "flagged": [model refs], "at",
        "proof_key"}``.
    """
    at = _now_iso()
    versions = _subject_dataset_versions(registry, store, subject_id)

    # Flag models first, while lineage/metadata is still fully intact.
    models = registry.models_for_subject(subject_id)
    flagged_refs: list[str] = []
    for model in models:
        updated = registry.flag_model(model.name, model.version, reason)
        flagged_refs.append(updated.ref)

    erased: list[dict[str, Any]] = []
    for dv in versions:
        blob_key = _blob_key(dv.name, dv.version)
        existed = store.exists(blob_key)
        store.delete(blob_key)
        _redact_dataset_meta(store, dv.name, dv.version, subject_id, reason)
        erased.append({"ref": dv.ref, "checksum": dv.checksum, "blob_existed": existed})

    erased_refs = [e["ref"] for e in erased]
    proof = {
        "subject_id": subject_id,
        "reason": reason,
        "erased": erased,
        "flagged": flagged_refs,
        "at": at,
    }
    proof["proof_hash"] = sha256_hex(canonical_json(proof).encode("utf-8"))
    stamp = at.replace(":", "").replace(".", "")
    proof_key = f"{_DELETION_PREFIX}/{subject_id}/{stamp}.json"
    store.put(proof_key, canonical_json(proof).encode("utf-8"))

    if audit is not None:
        audit.append(
            AuditEvent(
                actor="system",
                action="dsar.erase",
                target=subject_id,
                reason=reason,
                level="security",
                meta={
                    "erased": erased_refs,
                    "flagged": flagged_refs,
                    "proof_key": proof_key,
                },
            )
        )

    return {
        "subject_id": subject_id,
        "erased": erased_refs,
        "flagged": flagged_refs,
        "at": at,
        "proof_key": proof_key,
    }


def _redact_dataset_meta(
    store: ObjectStore, name: str, version: int, subject_id: str, reason: str
) -> None:
    """Remove ``subject_id`` from a dataset version's stored metadata, in place.

    Keeps the version record (for lineage/audit) but strips the subject reference
    and marks the version redacted, so a later subject scan no longer surfaces it.
    Written back in the same JSON shape the registry reads (``sort_keys``).
    """
    meta_key = f"{_DATASETS}/{name}/{version}/meta.json"
    try:
        meta = json.loads(store.get(meta_key).decode("utf-8"))
    except NotFound:
        return
    subjects = [s for s in meta.get("subjects", []) if s != subject_id]
    meta["subjects"] = subjects
    inner = dict(meta.get("meta", {}))
    inner["redacted"] = True
    inner["redaction_reason"] = reason
    meta["meta"] = inner
    store.put(meta_key, json.dumps(meta, sort_keys=True).encode("utf-8"))
