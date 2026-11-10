"""FR-45 acceptance: export then erase a data subject, end to end.

Extends FR-23 (find + flag): the subject's actual data is exported into a
portable package and then erased from the object store, with every affected
model flagged for retrain/removal and a tamper-evident deletion proof recorded.
"""

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


def test_fr45_export_then_erase_subject_end_to_end(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "store")
    reg = ObjectStoreRegistry(store)
    audit = AuditLog(path=tmp_path / "audit.jsonl")

    # Two dataset versions reference the subject; one model is trained on them.
    dv1 = ingest_dataset(
        reg,
        "patients",
        b"v1-alice",
        source="upload",
        sensitivity=SensitivityLabel.PHI,
        subjects=("alice",),
        approved_sources=APPROVED,
    )
    dv2 = ingest_dataset(
        reg,
        "notes",
        b"v1-alice-notes",
        source="upload",
        sensitivity=SensitivityLabel.PERSONAL,
        subjects=("alice",),
        approved_sources=APPROVED,
    )
    mv = reg.add_model(
        "triage",
        b"weights",
        lineage=LineageRecord(dataset_refs=(dv1.ref, dv2.ref)),
    )

    # 1. EXPORT: the subject gets a package listing both datasets + the model.
    out_store = LocalObjectStore(tmp_path / "export")
    manifest = export_subject_data(
        reg, store, "alice", out_store=out_store, audit=audit
    )
    assert set(manifest["datasets"]) == {dv1.ref, dv2.ref}
    assert manifest["models"] == [mv.ref]
    assert out_store.exists(manifest["package_key"])
    package = json.loads(out_store.get(manifest["package_key"]).decode("utf-8"))
    for entry in package["dataset_entries"]:
        assert out_store.exists(entry["blob_key"])

    # 2. ERASE: blobs removed, model flagged, deletion proof written.
    report = erase_subject_data(reg, store, "alice", audit=audit)
    assert set(report["erased"]) == {dv1.ref, dv2.ref}
    assert report["flagged"] == [mv.ref]

    assert store.exists(f"datasets/{dv1.name}/{dv1.version}/blob") is False
    assert store.exists(f"datasets/{dv2.name}/{dv2.version}/blob") is False
    assert reg.get_model(mv.name, mv.version).flagged is True
    assert store.exists(report["proof_key"])

    # 3. Both operations are on the tamper-evident audit trail.
    actions = [
        json.loads(line)["action"]
        for line in Path(audit.path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "dsar.export" in actions
    assert "dsar.erase" in actions
    assert audit.verify().ok is True
