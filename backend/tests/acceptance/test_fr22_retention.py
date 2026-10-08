"""Acceptance: scheduled per-dataset retention with auditable proof (FR-22)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gadziriro.core.crypto import hash_record
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.ingest import ingest_dataset
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.governance.retention import RetentionPolicy, apply_retention
from gadziriro.registry.store import ObjectStoreRegistry

APPROVED = {"upload"}


def test_fr22_per_dataset_retention_runs_with_auditable_proof(
    tmp_path: Path,
) -> None:
    store = LocalObjectStore(tmp_path / "store")
    reg = ObjectStoreRegistry(store)

    ingest_dataset(
        reg,
        "short_lived",
        b"expires soon",
        source="upload",
        sensitivity=SensitivityLabel.PERSONAL,
        approved_sources=APPROVED,
    )
    ingest_dataset(
        reg,
        "long_lived",
        b"keep me",
        source="upload",
        sensitivity=SensitivityLabel.INTERNAL,
        approved_sources=APPROVED,
    )

    policies = [
        RetentionPolicy("short_lived", retain_days=30),
        RetentionPolicy("long_lived", retain_days=3650),
    ]
    now = datetime.now(timezone.utc) + timedelta(days=90)

    proofs = apply_retention(reg, store, policies, now=now)

    # only the short-lived dataset is swept
    assert [p["dataset_ref"] for p in proofs] == ["short_lived@1"]
    assert not store.exists("datasets/short_lived/1/blob")
    assert store.exists("datasets/long_lived/1/blob")

    # the deletion left an auditable, tamper-evident proof on disk
    raw = store.get("deletion_proofs/short_lived/1.json")
    record = json.loads(raw.decode("utf-8"))
    assert record["dataset_ref"] == "short_lived@1"
    assert record["reason"]
    assert "deleted_at" in record
    assert "checksum_of_deleted" in record

    claimed = dict(record)
    proof_hash = claimed.pop("proof_hash")
    assert hash_record(claimed) == proof_hash
