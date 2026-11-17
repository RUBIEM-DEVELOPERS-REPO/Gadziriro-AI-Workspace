"""FR-26: a compliance officer exports one auditor evidence pack."""

from __future__ import annotations

import json

from gadziriro.audit.base import AuditEvent
from gadziriro.audit.log import AuditLog
from gadziriro.compliance.evidence import build_evidence_pack
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.store import ObjectStoreRegistry


def test_single_pack_bundles_all_evidence(tmp_path) -> None:
    store = LocalObjectStore(tmp_path / "store")
    reg = ObjectStoreRegistry(store)
    reg.add_dataset("patients", b"x", sensitivity=SensitivityLabel.PHI, source="nas")
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append(AuditEvent(actor="admin", action="export.approve", target="m@1"))
    out = LocalObjectStore(tmp_path / "out")

    manifest = build_evidence_pack(
        audit_log=log,
        registry=reg,
        object_store=store,
        enabled_packs=["hipaa"],
        out_store=out,
    )

    pack = json.loads(out.get(manifest["pack_key"]))
    assert pack["audit"]["ok"] is True and pack["audit"]["count"] == 1
    assert pack["policy"]["enabled"] == ["hipaa"]
    assert pack["policy"]["provenance"]
    assert pack["egress"]["total"] == 1
    assert pack["ropa"]["count"] == 1
    assert pack["sbom"]["component_count"] > 0
    assert out.exists(manifest["md_key"])
    assert {"audit", "policy", "egress", "ropa", "sbom"} <= set(manifest["sections"])
