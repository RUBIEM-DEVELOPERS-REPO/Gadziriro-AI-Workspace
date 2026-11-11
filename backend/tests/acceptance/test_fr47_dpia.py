"""FR-47 acceptance: create, fill, review and export a DPIA."""

from __future__ import annotations

import json

from gadziriro.compliance.dpia import DpiaRisk, DpiaService
from gadziriro.core.objectstore import LocalObjectStore


def test_dpia_end_to_end(tmp_path) -> None:
    svc = DpiaService()
    d = svc.create_dpia("Kuwana fine-tune DPIA", "PHI fine-tuning", "dpo@acme")
    svc.add_risk(
        d.dpia_id, DpiaRisk("model memorises PHI", "med", "high", "QLoRA + eval", "low")
    )
    svc.set_status(d.dpia_id, "in_review")
    svc.set_status(d.dpia_id, "approved")

    store = LocalObjectStore(tmp_path / "s")
    key = svc.export(d.dpia_id, store)
    payload = json.loads(store.get(key).decode("utf-8"))
    assert payload["status"] == "approved"
    assert any("PHI" in r["description"] for r in payload["risks"])
