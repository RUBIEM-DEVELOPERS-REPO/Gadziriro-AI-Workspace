"""FR-46 acceptance: export the register of personal-data processing."""

from __future__ import annotations

import json

from gadziriro.compliance.ropa import build_ropa, export_ropa
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.store import ObjectStoreRegistry


def test_export_ropa_register(tmp_path) -> None:
    store = LocalObjectStore(tmp_path / "store")
    reg = ObjectStoreRegistry(store)
    reg.add_dataset(
        "members", b"x", sensitivity=SensitivityLabel.PERSONAL, source="crm"
    )
    reg.add_dataset("logs", b"y", sensitivity=SensitivityLabel.INTERNAL, source="sys")

    activities = build_ropa(reg, store, controller="Acme Ltd")
    key = export_ropa(activities, store)
    register = json.loads(store.get(key).decode("utf-8"))

    assert len(register) == 1  # only the personal dataset
    assert register[0]["controller"] == "Acme Ltd"
    assert register[0]["data_categories"] == ["personal_data"]
