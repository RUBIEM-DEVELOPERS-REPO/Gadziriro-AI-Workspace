"""Unit tests for DSAR find + flag via lineage (FR-23)."""

from __future__ import annotations

from pathlib import Path

from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.dsar import erase_subject, find_subject_models
from gadziriro.governance.ingest import ingest_dataset
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry

APPROVED = {"upload"}


def _registry(tmp_path: Path) -> ObjectStoreRegistry:
    return ObjectStoreRegistry(LocalObjectStore(tmp_path / "store"))


def _build_model_for_alice(reg: ObjectStoreRegistry) -> str:
    dv = ingest_dataset(
        reg,
        "patients",
        b"rows",
        source="upload",
        sensitivity=SensitivityLabel.PHI,
        subjects=("alice",),
        approved_sources=APPROVED,
    )
    mv = reg.add_model(
        "triage",
        b"weights",
        lineage=LineageRecord(dataset_refs=(dv.ref,)),
    )
    return mv.ref


def test_find_subject_models_returns_the_model(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    model_ref = _build_model_for_alice(reg)

    found = find_subject_models(reg, "alice")
    assert [m.ref for m in found] == [model_ref]
    assert find_subject_models(reg, "mallory") == []


def test_erase_subject_flags_and_reports(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    model_ref = _build_model_for_alice(reg)

    report = erase_subject(reg, "alice")

    assert report["subject_id"] == "alice"
    assert report["flagged"] == [model_ref]
    assert "at" in report

    name, _, version = model_ref.partition("@")
    assert reg.get_model(name, int(version)).flagged is True
