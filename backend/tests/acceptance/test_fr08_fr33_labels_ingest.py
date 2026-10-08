"""Acceptance: labelled ingestion from approved sources only (FR-08, FR-33)."""

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


def test_fr08_every_ingested_dataset_is_labelled(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    cases = [
        ("public_stats", SensitivityLabel.PUBLIC, "upload", ()),
        ("ward_notes", SensitivityLabel.PERSONAL, "nas://ward4", ("alice",)),
        ("scans", SensitivityLabel.PHI, "s3://acme-approved", ("bob",)),
    ]
    for name, label, source, subjects in cases:
        ingest_dataset(
            reg,
            name,
            b"payload",
            source=source,
            sensitivity=label,
            subjects=subjects,
            approved_sources=APPROVED,
        )

    for name, label, _source, subjects in cases:
        stored = reg.get_dataset(name)
        assert stored.sensitivity is label
        assert isinstance(stored.sensitivity, SensitivityLabel)
        assert stored.subjects == subjects


def test_fr33_data_only_enters_from_approved_sources(tmp_path: Path) -> None:
    reg = _registry(tmp_path)

    # an approved source is admitted
    ingest_dataset(
        reg,
        "ok",
        b"data",
        source="s3://acme-approved",
        sensitivity=SensitivityLabel.INTERNAL,
        approved_sources=APPROVED,
    )
    assert reg.get_dataset("ok").source == "s3://acme-approved"

    # an unapproved source is rejected and nothing is persisted
    with pytest.raises(PolicyDenied):
        ingest_dataset(
            reg,
            "exfil",
            b"data",
            source="s3://random-bucket",
            sensitivity=SensitivityLabel.INTERNAL,
            approved_sources=APPROVED,
        )
    assert reg.list_dataset_versions("exfil") == []
