"""Unit tests for retention windows + scheduled deletion with proof (FR-22)."""

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


def _setup(tmp_path: Path) -> tuple[ObjectStoreRegistry, LocalObjectStore]:
    store = LocalObjectStore(tmp_path / "store")
    return ObjectStoreRegistry(store), store


def test_expired_version_deleted_with_verifiable_proof(tmp_path: Path) -> None:
    reg, store = _setup(tmp_path)
    ingest_dataset(
        reg,
        "old",
        b"stale",
        source="upload",
        sensitivity=SensitivityLabel.INTERNAL,
        approved_sources=APPROVED,
    )

    future = datetime.now(timezone.utc) + timedelta(days=30)
    proofs = apply_retention(
        reg,
        store,
        [RetentionPolicy("old", retain_days=7)],
        now=future,
    )

    assert len(proofs) == 1
    proof = proofs[0]
    assert proof["dataset_ref"] == "old@1"

    # the blobs are gone from the store
    assert not store.exists("datasets/old/1/blob")
    assert not store.exists("datasets/old/1/meta.json")

    # the deletion proof is persisted and tamper-evident
    raw = store.get("deletion_proofs/old/1.json")
    stored_proof = json.loads(raw.decode("utf-8"))
    assert stored_proof == proof

    recomputed = dict(stored_proof)
    claimed = recomputed.pop("proof_hash")
    assert hash_record(recomputed) == claimed


def test_fresh_version_is_retained(tmp_path: Path) -> None:
    reg, store = _setup(tmp_path)
    ingest_dataset(
        reg,
        "fresh",
        b"recent",
        source="upload",
        sensitivity=SensitivityLabel.INTERNAL,
        approved_sources=APPROVED,
    )

    future = datetime.now(timezone.utc) + timedelta(days=5)
    proofs = apply_retention(
        reg,
        store,
        [RetentionPolicy("fresh", retain_days=3650)],
        now=future,
    )

    assert proofs == []
    assert store.exists("datasets/fresh/1/blob")
    assert reg.list_dataset_versions("fresh")[0].ref == "fresh@1"


def test_injected_now_drives_deletion(tmp_path: Path) -> None:
    reg, store = _setup(tmp_path)
    ingest_dataset(
        reg,
        "ds",
        b"x",
        source="upload",
        sensitivity=SensitivityLabel.INTERNAL,
        approved_sources=APPROVED,
    )
    policy = RetentionPolicy("ds", retain_days=10)

    # before the window elapses: retained
    early = datetime.now(timezone.utc) + timedelta(days=3)
    assert apply_retention(reg, store, [policy], now=early) == []
    assert store.exists("datasets/ds/1/blob")

    # after the window elapses: deleted
    late = datetime.now(timezone.utc) + timedelta(days=20)
    proofs = apply_retention(reg, store, [policy], now=late)
    assert len(proofs) == 1
    assert not store.exists("datasets/ds/1/blob")


def test_retain_until_absolute_cutoff(tmp_path: Path) -> None:
    reg, store = _setup(tmp_path)
    ingest_dataset(
        reg,
        "ds",
        b"x",
        source="upload",
        sensitivity=SensitivityLabel.INTERNAL,
        approved_sources=APPROVED,
    )
    policy = RetentionPolicy("ds", retain_until="2000-01-01")
    proofs = apply_retention(reg, store, [policy])
    assert len(proofs) == 1
    assert not store.exists("datasets/ds/1/blob")
