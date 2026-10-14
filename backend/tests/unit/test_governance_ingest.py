"""Unit tests for approved-source ingestion + labelling (FR-33, FR-08)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.errors import PolicyDenied
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.ingest import ingest_dataset
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.store import ObjectStoreRegistry

APPROVED = {"s3://acme-approved", "nas://ward4", "upload"}


def _registry(tmp_path: Path) -> ObjectStoreRegistry:
    return ObjectStoreRegistry(LocalObjectStore(tmp_path / "store"))


def test_ingest_from_approved_source_labels_and_stores(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    dv = ingest_dataset(
        reg,
        "patients",
        b"rows",
        source="nas://ward4",
        sensitivity=SensitivityLabel.PHI,
        subjects=("alice", "bob"),
        approved_sources=APPROVED,
    )

    assert dv.sensitivity is SensitivityLabel.PHI
    assert dv.subjects == ("alice", "bob")
    assert dv.source == "nas://ward4"

    stored = reg.get_dataset("patients")
    assert stored.sensitivity is SensitivityLabel.PHI
    assert stored.subjects == ("alice", "bob")


def test_ingest_accepts_sensitivity_as_string(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    dv = ingest_dataset(
        reg,
        "notes",
        b"data",
        source="upload",
        sensitivity="personal",
        approved_sources=APPROVED,
    )
    assert dv.sensitivity is SensitivityLabel.PERSONAL


def test_ingest_from_unapproved_source_denies_and_stores_nothing(
    tmp_path: Path,
) -> None:
    reg = _registry(tmp_path)
    with pytest.raises(PolicyDenied):
        ingest_dataset(
            reg,
            "leak",
            b"data",
            source="http://random-upload",
            sensitivity=SensitivityLabel.INTERNAL,
            approved_sources=APPROVED,
        )

    assert reg.list_dataset_versions("leak") == []
