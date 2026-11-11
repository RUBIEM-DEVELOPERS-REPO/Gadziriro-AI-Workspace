"""Unit tests for the DPIA workflow."""

from __future__ import annotations

import json

import pytest

from gadziriro.compliance.dpia import DpiaRisk, DpiaService
from gadziriro.core.errors import GadziriroError, NotFound
from gadziriro.core.objectstore import LocalObjectStore


def test_create_from_template_seeds_risks() -> None:
    svc = DpiaService()
    d = svc.create_dpia("Model X DPIA", "fine-tuning on client data", "dpo")
    assert d.status == "draft"
    assert len(d.risks) >= 4


def test_add_risk_and_status_flow() -> None:
    svc = DpiaService()
    d = svc.create_dpia("t", "s", "dpo", from_template=False)
    assert d.risks == []
    svc.add_risk(d.dpia_id, DpiaRisk("new risk", "low", "low", "mitigate", "low"))
    assert len(svc.get(d.dpia_id).risks) == 1
    svc.set_status(d.dpia_id, "in_review")
    svc.set_status(d.dpia_id, "approved")
    assert svc.get(d.dpia_id).status == "approved"


def test_invalid_transition_and_unknown() -> None:
    svc = DpiaService()
    d = svc.create_dpia("t", "s", "dpo")
    with pytest.raises(GadziriroError):
        svc.set_status(d.dpia_id, "approved")  # can't skip in_review
    with pytest.raises(GadziriroError):
        svc.set_status(d.dpia_id, "bogus")
    with pytest.raises(NotFound):
        svc.get("missing")


def test_export(tmp_path) -> None:
    svc = DpiaService()
    d = svc.create_dpia("t", "s", "dpo")
    store = LocalObjectStore(tmp_path / "s")
    key = svc.export(d.dpia_id, store)
    payload = json.loads(store.get(key).decode("utf-8"))
    assert payload["dpia_id"] == d.dpia_id
    assert "not legal advice" in payload["note"]
