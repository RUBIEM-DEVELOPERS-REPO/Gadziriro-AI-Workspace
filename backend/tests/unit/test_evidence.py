"""Unit tests for the auditor evidence pack (FR-26)."""

from __future__ import annotations

import json

from gadziriro.audit.base import AuditEvent
from gadziriro.audit.log import AuditLog
from gadziriro.compliance.evidence import build_evidence_pack
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.store import ObjectStoreRegistry


def _setup(tmp_path):
    store = LocalObjectStore(tmp_path / "store")
    reg = ObjectStoreRegistry(store)
    reg.add_dataset(
        "clients", b"x", sensitivity=SensitivityLabel.PERSONAL, source="crm"
    )
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append(AuditEvent(actor="alice", action="export.request", target="m@1"))
    log.append(AuditEvent(actor="admin", action="export.approve", target="m@1"))
    return store, reg, log


def _build(tmp_path, log, reg, store):
    out = LocalObjectStore(tmp_path / "out")
    manifest = build_evidence_pack(
        audit_log=log,
        registry=reg,
        object_store=store,
        enabled_packs=["gdpr"],
        out_store=out,
    )
    return out, manifest


def test_pack_written_with_sections(tmp_path) -> None:
    store, reg, log = _setup(tmp_path)
    out, manifest = _build(tmp_path, log, reg, store)
    assert manifest["audit_ok"] is True
    assert manifest["pack_key"].startswith("evidence/pack-")
    assert manifest["md_key"].endswith(".md")
    pack = json.loads(out.get(manifest["pack_key"]))
    for section in ("audit", "policy", "egress", "ropa", "sbom"):
        assert section in pack
    assert pack["audit"]["count"] == 2
    assert pack["egress"]["approved_count"] == 1
    assert pack["ropa"]["dataset_refs"] == ["clients@1"]
    assert pack["policy"]["enabled"] == ["gdpr"]
    assert "legal review" in pack["note"]
    assert "Auditor Evidence Pack" in out.get(manifest["md_key"]).decode()


def test_tampering_reported(tmp_path) -> None:
    store, reg, log = _setup(tmp_path)
    log.path.write_text(
        log.path.read_text(encoding="utf-8").replace("alice", "mallory"),
        encoding="utf-8",
    )
    out, manifest = _build(tmp_path, log, reg, store)
    assert manifest["audit_ok"] is False
    assert json.loads(out.get(manifest["pack_key"]))["audit"]["ok"] is False
