"""Unit tests for DSAR export + erase of the data itself (FR-45)."""

from __future__ import annotations

import json
from pathlib import Path

from gadziriro.audit.log import AuditLog
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.dsar_export import erase_subject_data, export_subject_data
from gadziriro.governance.ingest import ingest_dataset
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry

APPROVED = {"upload"}


def _setup(tmp_path: Path):
    store = LocalObjectStore(tmp_path / "store")
    reg = ObjectStoreRegistry(store)
    dv = ingest_dataset(
        reg,
        "patients",
        b"alice-rows",
        source="upload",
        sensitivity=SensitivityLabel.PHI,
        subjects=("alice", "carol"),
        approved_sources=APPROVED,
    )
    mv = reg.add_model(
        "triage",
        b"weights",
        lineage=LineageRecord(dataset_refs=(dv.ref,)),
    )
    return store, reg, dv, mv


def test_export_writes_package_with_datasets_and_models(tmp_path: Path) -> None:
    store, reg, dv, mv = _setup(tmp_path)
    out_store = LocalObjectStore(tmp_path / "out")
    audit = AuditLog(path=tmp_path / "audit.jsonl")

    manifest = export_subject_data(
        reg, store, "alice", out_store=out_store, audit=audit
    )

    assert manifest["subject_id"] == "alice"
    assert manifest["datasets"] == [dv.ref]
    assert manifest["models"] == [mv.ref]
    assert "exported_at" in manifest
    package_key = manifest["package_key"]
    assert out_store.exists(package_key)

    # The subject's dataset blob was copied into the export package.
    stored = json.loads(out_store.get(package_key).decode("utf-8"))
    for entry in stored["dataset_entries"]:
        assert out_store.exists(entry["blob_key"])

    actions = [e["action"] for e in _events(audit)]
    assert "dsar.export" in actions


def test_export_ignores_unrelated_subject(tmp_path: Path) -> None:
    store, reg, _dv, _mv = _setup(tmp_path)
    out_store = LocalObjectStore(tmp_path / "out")

    manifest = export_subject_data(reg, store, "mallory", out_store=out_store)
    assert manifest["datasets"] == []
    assert manifest["models"] == []


def test_erase_removes_blob_flags_model_and_proves_deletion(tmp_path: Path) -> None:
    store, reg, dv, mv = _setup(tmp_path)
    audit = AuditLog(path=tmp_path / "audit.jsonl")

    blob_key = f"datasets/{dv.name}/{dv.version}/blob"
    assert store.exists(blob_key) is True

    report = erase_subject_data(reg, store, "alice", audit=audit)

    assert report["subject_id"] == "alice"
    assert report["erased"] == [dv.ref]
    assert report["flagged"] == [mv.ref]
    assert "at" in report

    # The raw dataset blob is gone.
    assert store.exists(blob_key) is False

    # The model is flagged for retrain/removal.
    assert reg.get_model(mv.name, mv.version).flagged is True

    # A deletion proof was written and references the erased ref.
    proof_key = report["proof_key"]
    assert store.exists(proof_key)
    proof = json.loads(store.get(proof_key).decode("utf-8"))
    assert proof["subject_id"] == "alice"
    assert "proof_hash" in proof
    assert any(e["ref"] == dv.ref for e in proof["erased"])

    # Erasure is audited.
    actions = [e["action"] for e in _events(audit)]
    assert "dsar.erase" in actions
    assert audit.verify().ok is True


def test_erase_redacts_subject_from_metadata(tmp_path: Path) -> None:
    store, reg, dv, _mv = _setup(tmp_path)
    erase_subject_data(reg, store, "alice")

    # "carol" remained; "alice" is scrubbed from the version metadata.
    refreshed = reg.get_dataset(dv.name, dv.version)
    assert "alice" not in refreshed.subjects
    assert "carol" in refreshed.subjects


def _events(audit: AuditLog) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(audit.path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
