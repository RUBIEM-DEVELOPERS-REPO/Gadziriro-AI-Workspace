"""Unit tests for the object-store-backed registry (FR-06, FR-07)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.crypto import sha256_hex
from gadziriro.core.errors import NotFound
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry


def _registry(tmp_path: Path) -> ObjectStoreRegistry:
    return ObjectStoreRegistry(LocalObjectStore(tmp_path / "store"))


def test_dataset_versions_are_monotonic_from_one(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    v1 = reg.add_dataset(
        "ds", b"one", sensitivity=SensitivityLabel.INTERNAL, source="s"
    )
    v2 = reg.add_dataset(
        "ds", b"two", sensitivity=SensitivityLabel.INTERNAL, source="s"
    )
    assert v1.version == 1
    assert v2.version == 2


def test_get_latest_and_rollback_to_older_version(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.add_dataset("ds", b"one", sensitivity=SensitivityLabel.INTERNAL, source="s")
    v2 = reg.add_dataset(
        "ds", b"two", sensitivity=SensitivityLabel.INTERNAL, source="s"
    )

    latest = reg.get_dataset("ds")
    assert latest.version == v2.version == 2

    # FR-06 rollback: pinning an explicit older version.
    rolled_back = reg.get_dataset("ds", version=1)
    assert rolled_back.version == 1
    assert rolled_back.checksum == sha256_hex(b"one")


def test_dataset_checksum_matches_content(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    dv = reg.add_dataset(
        "ds", b"payload", sensitivity=SensitivityLabel.PHI, source="ehr"
    )
    assert dv.checksum == sha256_hex(b"payload")
    assert dv.sensitivity is SensitivityLabel.PHI
    assert dv.source == "ehr"


def test_list_dataset_versions(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.add_dataset("ds", b"a", sensitivity=SensitivityLabel.INTERNAL, source="s")
    reg.add_dataset("ds", b"b", sensitivity=SensitivityLabel.INTERNAL, source="s")
    versions = reg.list_dataset_versions("ds")
    assert [d.version for d in versions] == [1, 2]


def test_models_from_dataset_finds_model_by_lineage(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.add_dataset("ds", b"a", sensitivity=SensitivityLabel.INTERNAL, source="s")
    reg.add_dataset("ds", b"b", sensitivity=SensitivityLabel.INTERNAL, source="s")

    lineage = LineageRecord(
        dataset_refs=("ds@2",),
        code_ref="abc123",
        params={"lr": 0.01},
        hardware="1xA100-80GB",
    )
    mv = reg.add_model("m", b"weights", lineage=lineage)

    found = reg.models_from_dataset("ds@2")
    assert [m.ref for m in found] == [mv.ref]
    # The dataset that was NOT used does not match.
    assert reg.models_from_dataset("ds@1") == []


def test_models_for_subject_resolves_via_lineage(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.add_dataset(
        "ds",
        b"a",
        sensitivity=SensitivityLabel.PERSONAL,
        source="s",
        subjects=("alice",),
    )
    mv = reg.add_model("m", b"weights", lineage=LineageRecord(dataset_refs=("ds@1",)))

    assert [m.ref for m in reg.models_for_subject("alice")] == [mv.ref]
    assert reg.models_for_subject("bob") == []


def test_flag_model_sets_flagged_and_persists(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.add_model("m", b"w", lineage=LineageRecord(dataset_refs=()))

    assert reg.get_model("m").flagged is False
    flagged = reg.flag_model("m", 1, reason="DSAR erasure for alice")
    assert flagged.flagged is True
    assert flagged.meta["flag_reason"] == "DSAR erasure for alice"
    # Persisted across reloads.
    assert reg.get_model("m", 1).flagged is True


def test_notfound_on_missing(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    with pytest.raises(NotFound):
        reg.get_dataset("missing")
    with pytest.raises(NotFound):
        reg.get_model("missing")

    reg.add_dataset("ds", b"a", sensitivity=SensitivityLabel.INTERNAL, source="s")
    with pytest.raises(NotFound):
        reg.get_dataset("ds", version=99)
    with pytest.raises(NotFound):
        reg.flag_model("missing", 1, reason="x")
