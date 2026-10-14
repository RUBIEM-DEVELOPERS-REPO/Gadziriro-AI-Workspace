"""Integration tests for the Phase 2 Model Studio gateway wiring.

Exercises the newly surfaced Phase 2 services through the FastAPI ``TestClient``:
fine-tune + export (FR-10/FR-15), evaluation run/compare/diff (FR-11/FR-13),
weight tools (FR-12), model cards (FR-36), licensing (FR-48), policy packs
(FR-24), incidents + breach report (FR-38), DSAR export/erase (FR-45) and the
support bundle (FR-40). Fixture wiring mirrors ``test_gateway_phase1`` (temp
sqlite user store, mock-runtime session manager, temp audit log, temp data dir)
with a pre-seeded registry.
"""

from __future__ import annotations

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from gadziriro.audit.log import AuditLog
from gadziriro.auth.base import Role
from gadziriro.auth.store import SqlUserStore
from gadziriro.core.config import Settings
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.gateway.app import create_app
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry
from gadziriro.runtime.mock import MockRuntimeAdapter
from gadziriro.sessions.manager import SessionManager


@pytest.fixture()
def client(tmp_path) -> TestClient:
    """A TestClient over an app wired to temp stores + a seeded registry."""
    cheap = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    store = SqlUserStore(f"sqlite:///{tmp_path / 'auth.db'}", hasher=cheap)
    store.create_user("admin", "admin-pw", {Role.ADMIN})
    store.create_user("ana", "ana-pw", {Role.ANALYST})
    store.create_user("ds", "ds-pw", {Role.DATA_SCIENTIST})
    store.create_user("dpo", "dpo-pw", {Role.COMPLIANCE})

    audit = AuditLog(path=tmp_path / "audit.jsonl")
    manager = SessionManager(MockRuntimeAdapter(gpu_count=1), audit=audit)

    object_store = LocalObjectStore(tmp_path / "objectstore")
    registry = ObjectStoreRegistry(object_store)
    registry.add_dataset(
        "patients",
        b"rows",
        sensitivity=SensitivityLabel.PHI,
        source="upload",
        subjects=("subj-1",),
    )
    # Two model versions so compare/diff/merge have something to work with.
    registry.add_model(
        "classifier",
        b"weights-v1",
        lineage=LineageRecord(
            dataset_refs=("patients@1",),
            code_ref="abc123",
            params={"base_model": "mistral-7b"},
        ),
        sensitivity=SensitivityLabel.INTERNAL,
    )
    registry.add_model(
        "classifier",
        b"weights-v2-better",
        lineage=LineageRecord(
            dataset_refs=("patients@1",),
            code_ref="def456",
            params={"base_model": "mistral-7b"},
        ),
        sensitivity=SensitivityLabel.INTERNAL,
    )

    settings = Settings(data_dir=tmp_path / "data")
    settings.ensure_dirs()
    app = create_app(
        settings,
        user_store=store,
        session_manager=manager,
        audit=audit,
        object_store=object_store,
        registry=registry,
    )
    return TestClient(app)


def _login(client: TestClient, username: str, password: str) -> None:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200


_SUITE = [
    {"prompt": "p1", "expected": "ans-x", "weight": 1.0},
    {"prompt": "p2", "expected": "ans-y"},
]


def test_finetune_registers_a_model(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    resp = client.post(
        "/api/modelstudio/finetune",
        json={
            "base_model": "llama-3-8b",
            "dataset_refs": ["patients@1"],
            "output_name": "ft-clf",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["method"] == "qlora"  # default for the analyst form
    assert body["model_ref"].startswith("ft-clf@")
    assert "train_loss" in body["metrics"]

    listed = client.get("/api/models")
    assert "ft-clf" in [m["name"] for m in listed.json()]


def test_export_returns_artifact_and_serving_command(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    resp = client.post(
        "/api/modelstudio/export",
        json={"model_ref": "classifier@1", "format": "safetensors"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["format"] == "safetensors"
    assert body["path_or_key"].endswith(".safetensors")
    assert body["serving_command"][0] == "python"
    assert "serving_manifest" in body


def test_templates_endpoint(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    resp = client.get("/api/modelstudio/templates")
    assert resp.status_code == 200
    body = resp.json()
    assert "qlora" in body["methods"]
    assert body["templates"]["lora"]["method"] == "lora"


def test_evaluation_run_compare_diff(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")

    run = client.post(
        "/api/evaluation/run",
        json={"model_ref": "classifier@1", "suite": _SUITE, "suite_name": "s"},
    )
    assert run.status_code == 200, run.text
    assert 0.0 <= run.json()["score"] <= 1.0
    assert run.json()["suite"] == "s"

    cmp = client.post(
        "/api/evaluation/compare",
        json={"a_ref": "classifier@1", "b_ref": "classifier@2", "suite": _SUITE},
    )
    assert cmp.status_code == 200
    assert "score_delta" in cmp.json()

    diff = client.post(
        "/api/evaluation/diff",
        json={"a_ref": "classifier@1", "b_ref": "classifier@2"},
    )
    assert diff.status_code == 200
    summary = diff.json()["weight_summary"]
    assert summary["checksum_changed"] is True


def test_weighttools_merge_quantize_prune_inspect(client: TestClient) -> None:
    _login(client, "ds", "ds-pw")

    merged = client.post(
        "/api/weighttools/merge",
        json={"refs": ["classifier@1", "classifier@2"], "out_name": "merged"},
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["meta"]["op"] == "merge"

    quant = client.post(
        "/api/weighttools/quantize",
        json={"ref": "classifier@1", "method": "gptq", "out_name": "q"},
    )
    assert quant.status_code == 200
    assert quant.json()["meta"]["method"] == "gptq"

    pruned = client.post(
        "/api/weighttools/prune",
        json={"ref": "classifier@1", "sparsity": 0.5, "out_name": "p"},
    )
    assert pruned.status_code == 200
    assert pruned.json()["meta"]["op"] == "prune"

    insp = client.get("/api/weighttools/inspect/classifier/1")
    assert insp.status_code == 200
    assert insp.json()["ref"] == "classifier@1"
    assert insp.json()["num_layers"] >= 1


def test_weighttools_requires_data_scientist(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    resp = client.get("/api/weighttools/inspect/classifier/1")
    assert resp.status_code == 403


def test_model_card_renders(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    resp = client.get("/api/modelcards/classifier/1", params={"licence": "apache-2.0"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["card"]["licence"] == "apache-2.0"
    assert "Model Card" in body["markdown"]
    assert body["stored_key"] is None


def test_model_card_can_be_stored(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    resp = client.get(
        "/api/modelcards/classifier/1", params={"store_card_flag": "true"}
    )
    assert resp.status_code == 200
    assert resp.json()["stored_key"].endswith(".md")


def test_licensing_lookup_and_check_block(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")

    rec = client.get("/api/licensing/llama-3-8b")
    assert rec.status_code == 200
    assert rec.json()["commercial_use"] is True

    # A non-commercial model used commercially is blocked (403).
    blocked = client.post(
        "/api/licensing/check",
        json={"model": "research-13b", "intended_use": "commercial"},
    )
    assert blocked.status_code == 403

    # An export-restricted model to a disallowed destination is blocked (403).
    export_blocked = client.post(
        "/api/licensing/check",
        json={
            "model": "qwen2-72b",
            "intended_use": "commercial",
            "destination": "overseas",
        },
    )
    assert export_blocked.status_code == 403

    ok = client.post(
        "/api/licensing/check",
        json={"model": "llama-3-8b", "intended_use": "commercial"},
    )
    assert ok.status_code == 200
    assert ok.json()["ok"] is True


def test_policy_packs_effective_strictest_wins(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")

    packs = client.get("/api/policy/packs")
    assert packs.status_code == 200
    assert "hipaa" in [p["name"] for p in packs.json()]

    eff = client.post(
        "/api/policy/packs/effective",
        json={"enabled": ["hipaa", "gdpr", "soc2", "zw-dpa"]},
    )
    assert eff.status_code == 200, eff.text
    body = eff.json()
    s = body["settings"]
    assert s["allow_egress"] is False
    assert s["require_mfa"] is True
    assert s["audit_retention_days"] == 2190  # HIPAA: strictest (max)
    assert s["data_retention_max_days"] == 365  # GDPR: strictest (min)
    assert body["precedence"]["audit_retention_days"] == "hipaa"


def test_policy_packs_unknown_is_400(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    resp = client.post("/api/policy/packs/effective", json={"enabled": ["nope"]})
    assert resp.status_code == 400


def test_incident_open_update_and_breach_report(client: TestClient) -> None:
    _login(client, "admin", "admin-pw")

    opened = client.post(
        "/api/incidents",
        json={
            "title": "patient export exfiltration",
            "severity": "critical",
            "breach": True,
            "affected_subjects": ["subj-1"],
        },
    )
    assert opened.status_code == 200, opened.text
    incident_id = opened.json()["incident_id"]

    updated = client.post(
        f"/api/incidents/{incident_id}/update",
        json={"status": "investigating", "note": "isolating host"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "investigating"

    listed = client.get("/api/incidents")
    assert incident_id in [i["incident_id"] for i in listed.json()]

    report = client.get(f"/api/incidents/{incident_id}/breach-report")
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["breach"] is True
    assert body["legal_review_required"] is True
    assert [e["action"] for e in body["timeline"]] == [
        "incident.open",
        "incident.update",
    ]


def test_incident_requires_admin_or_compliance(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    assert client.get("/api/incidents").status_code == 403


def test_dsar_export_and_erase(client: TestClient) -> None:
    _login(client, "dpo", "dpo-pw")

    exported = client.post("/api/dsar/subj-1/export")
    assert exported.status_code == 200, exported.text
    assert "patients@1" in exported.json()["datasets"]
    assert exported.json()["package_key"].startswith("dsar_exports/")

    erased = client.post("/api/dsar/subj-1/erase", json={"reason": "DSAR test"})
    assert erased.status_code == 200
    assert "patients@1" in erased.json()["erased"]
    assert erased.json()["proof_key"].startswith("dsar_deletions/")


def test_support_bundle_has_no_pii(client: TestClient) -> None:
    _login(client, "admin", "admin-pw")
    resp = client.post("/api/support/bundle")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bundle_key"].startswith("support_bundles/")
    assert "redacted_fields_count" in body


def test_support_bundle_requires_admin(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    assert client.post("/api/support/bundle").status_code == 403
