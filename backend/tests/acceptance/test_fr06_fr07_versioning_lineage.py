"""Acceptance tests: versioning + rollback (FR-06) and lineage/DSAR (FR-07).

These exercise the end-to-end story the requirements describe:

* FR-06 — datasets and models are versioned; an explicit older version is a
  rollback.
* FR-07 — every model traces back to the exact datasets, code, params and
  hardware that produced it, and that lineage supports the DSAR query path
  (find every model built from a given subject's data).
"""

from __future__ import annotations

from pathlib import Path

from gadziriro.core.crypto import sha256_hex
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry
from gadziriro.tracking.store import ObjectStoreTracker


def _registry(tmp_path: Path) -> ObjectStoreRegistry:
    return ObjectStoreRegistry(LocalObjectStore(tmp_path / "store"))


def test_fr06_versioning_and_rollback_end_to_end(tmp_path: Path) -> None:
    reg = _registry(tmp_path)

    v1 = reg.add_dataset(
        "patients", b"cohort-v1", sensitivity=SensitivityLabel.PHI, source="ehr"
    )
    v2 = reg.add_dataset(
        "patients", b"cohort-v2", sensitivity=SensitivityLabel.PHI, source="ehr"
    )
    assert (v1.version, v2.version) == (1, 2)

    # Latest is v2.
    assert reg.get_dataset("patients").version == 2
    assert reg.get_dataset("patients").checksum == sha256_hex(b"cohort-v2")

    # FR-06 rollback: pin the previous version explicitly.
    pinned = reg.get_dataset("patients", version=1)
    assert pinned.version == 1
    assert pinned.checksum == sha256_hex(b"cohort-v1")

    # Model versioning is monotonic the same way.
    m1 = reg.add_model(
        "clf", b"w1", lineage=LineageRecord(dataset_refs=("patients@1",))
    )
    m2 = reg.add_model(
        "clf", b"w2", lineage=LineageRecord(dataset_refs=("patients@2",))
    )
    assert (m1.version, m2.version) == (1, 2)
    assert reg.get_model("clf").version == 2
    assert reg.get_model("clf", version=1).version == 1


def test_fr07_model_traces_back_to_exact_inputs(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    tracker = ObjectStoreTracker(LocalObjectStore(tmp_path / "runs"))

    reg.add_dataset(
        "patients",
        b"cohort",
        sensitivity=SensitivityLabel.PHI,
        source="ehr",
        subjects=("alice", "bob"),
    )
    reg.add_dataset(
        "notes", b"txt", sensitivity=SensitivityLabel.PERSONAL, source="emr"
    )

    # A tracked run captures the reproducibility context (FR-09) ...
    run = tracker.start_run(
        params={"epochs": 3, "lr": 0.001},
        dataset_refs=("patients@1", "notes@1"),
        code_ref="git:abc123",
        hardware="1xA100-80GB",
    )
    tracker.log_metric(run.run_id, "auc", 0.91)
    tracker.end_run(run.run_id)

    # ... and the model's lineage names those exact inputs (FR-07).
    lineage = LineageRecord(
        dataset_refs=("patients@1", "notes@1"),
        code_ref="git:abc123",
        params={"epochs": 3, "lr": 0.001},
        hardware="1xA100-80GB",
        run_id=run.run_id,
    )
    model = reg.add_model("clf", b"weights", lineage=lineage)

    traced = reg.get_model("clf").lineage
    assert traced.dataset_refs == ("patients@1", "notes@1")
    assert traced.code_ref == "git:abc123"
    assert traced.params == {"epochs": 3, "lr": 0.001}
    assert traced.hardware == "1xA100-80GB"
    assert traced.run_id == run.run_id

    # The run record is enough to reproduce the exact inputs.
    reproduced = tracker.get_run(run.run_id)
    assert reproduced.dataset_refs == traced.dataset_refs
    assert reproduced.params == traced.params
    assert reproduced.code_ref == traced.code_ref
    assert reproduced.hardware == traced.hardware

    # Reverse lineage: which models used a given dataset version?
    assert [m.ref for m in reg.models_from_dataset("patients@1")] == [model.ref]


def test_fr07_lineage_supports_dsar_query_path(tmp_path: Path) -> None:
    reg = _registry(tmp_path)

    reg.add_dataset(
        "patients",
        b"cohort",
        sensitivity=SensitivityLabel.PHI,
        source="ehr",
        subjects=("alice",),
    )
    model = reg.add_model(
        "clf", b"weights", lineage=LineageRecord(dataset_refs=("patients@1",))
    )

    # DSAR: find every model built from alice's data via lineage resolution.
    hits = reg.models_for_subject("alice")
    assert [m.ref for m in hits] == [model.ref]
    assert reg.models_for_subject("carol") == []

    # DSAR erasure flags the affected model (FR-23) and the flag persists.
    flagged = reg.flag_model(model.name, model.version, reason="erasure request: alice")
    assert flagged.flagged is True
    assert reg.get_model("clf", model.version).flagged is True
