"""Unit tests for ROPA export."""

from __future__ import annotations

import json

from gadziriro.compliance.ropa import build_ropa, export_ropa
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.store import ObjectStoreRegistry


def _registry(tmp_path):
    store = LocalObjectStore(tmp_path / "store")
    reg = ObjectStoreRegistry(store)
    return store, reg


def test_ropa_includes_only_personal(tmp_path) -> None:
    store, reg = _registry(tmp_path)
    reg.add_dataset(
        "patients",
        b"x",
        sensitivity=SensitivityLabel.PHI,
        source="nas",
        subjects=("a",),
    )
    reg.add_dataset(
        "public_corpus", b"y", sensitivity=SensitivityLabel.PUBLIC, source="upload"
    )
    activities = build_ropa(reg, store)
    refs = {a.dataset_ref for a in activities}
    assert "patients@1" in refs
    assert not any(r.startswith("public_corpus") for r in refs)
    act = next(a for a in activities if a.dataset_ref == "patients@1")
    assert act.data_categories == ("health_data",)
    assert act.lawful_basis == "legitimate_interest"


def test_purposes_override_and_export(tmp_path) -> None:
    store, reg = _registry(tmp_path)
    reg.add_dataset(
        "clients", b"x", sensitivity=SensitivityLabel.PERSONAL, source="crm"
    )
    activities = build_ropa(reg, store, purposes={"clients": "CRM analytics"})
    assert activities[0].purpose == "CRM analytics"
    key = export_ropa(activities, store)
    data = json.loads(store.get(key).decode("utf-8"))
    assert data[0]["dataset_ref"] == "clients@1"
    assert store.exists("ropa/ropa.md")
