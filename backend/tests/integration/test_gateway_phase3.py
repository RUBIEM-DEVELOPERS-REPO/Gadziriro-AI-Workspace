"""Integration tests for the Phase 3 gateway wiring.

Signed updates (FR-30), dataset ACLs (FR-18b), egress report (FR-25), bias /
red-team safety checks (FR-37), ROPA (FR-46) and DPIA (FR-47) through the
FastAPI ``TestClient``, with role gating. Fixture wiring mirrors Phase 2.
"""

from __future__ import annotations

import base64

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from gadziriro.audit.base import AuditEvent
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
from gadziriro.updates.signing import build_update


@pytest.fixture()
def client(tmp_path) -> TestClient:
    cheap = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    store = SqlUserStore(f"sqlite:///{tmp_path / 'auth.db'}", hasher=cheap)
    store.create_user("admin", "admin-pw", {Role.ADMIN})
    store.create_user("ana", "ana-pw", {Role.ANALYST})
    store.create_user("ds", "ds-pw", {Role.DATA_SCIENTIST})
    store.create_user("dpo", "dpo-pw", {Role.COMPLIANCE})

    audit = AuditLog(path=tmp_path / "audit.jsonl")
    audit.append(AuditEvent(actor="ana", action="export.request", target="patients@1"))
    audit.append(AuditEvent(actor="admin", action="export.deny", target="patients@1"))
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
    registry.add_dataset(
        "public-stats", b"x", sensitivity=SensitivityLabel.PUBLIC, source="upload"
    )
    registry.add_model(
        "classifier",
        b"weights",
        lineage=LineageRecord(dataset_refs=("patients@1",), code_ref="abc"),
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


def _bundle(client: TestClient, version: str, *, key=None) -> str:
    key = key or client.app.state.update_dev_signing_key
    bundle, _ = build_update(version, b"payload", key)
    return base64.b64encode(bundle).decode()


def test_update_apply_rollback_history(client: TestClient) -> None:
    _login(client, "admin", "admin-pw")
    resp = client.post(
        "/api/updates/apply", json={"bundle_b64": _bundle(client, "0.2.0")}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["current_version"] == "0.2.0"

    resp = client.post("/api/updates/rollback")
    assert resp.status_code == 200
    assert resp.json()["current_version"] == "0.1.0"

    hist = client.get("/api/updates/history").json()
    assert hist["current_version"] == "0.1.0"
    assert [h["action"] for h in hist["history"]] == ["apply", "rollback"]


def test_update_rejects_forged_and_bad_base64(client: TestClient) -> None:
    from nacl.signing import SigningKey

    _login(client, "admin", "admin-pw")
    forged = _bundle(client, "0.9.0", key=SigningKey.generate())
    assert (
        client.post("/api/updates/apply", json={"bundle_b64": forged}).status_code
        == 400
    )
    assert (
        client.post("/api/updates/apply", json={"bundle_b64": "!!!"}).status_code == 400
    )
    assert client.post("/api/updates/rollback").status_code == 400  # nothing applied


def test_update_routes_admin_only(client: TestClient) -> None:
    _login(client, "dpo", "dpo-pw")
    body = {"bundle_b64": _bundle(client, "0.2.0")}
    assert client.post("/api/updates/apply", json=body).status_code == 403
    assert client.post("/api/updates/rollback").status_code == 403
    assert client.get("/api/updates/history").status_code == 403


def test_dataset_acl_put_get(client: TestClient) -> None:
    _login(client, "admin", "admin-pw")
    assert client.get("/api/datasets/patients/acl").status_code == 404
    resp = client.put(
        "/api/datasets/patients/acl",
        json={"allow_roles": ["data_scientist"], "deny_users": ["u9"]},
    )
    assert resp.status_code == 200, resp.text
    got = client.get("/api/datasets/patients/acl").json()
    assert got["allow_roles"] == ["data_scientist"]
    assert got["deny_users"] == ["u9"]
    bad = client.put("/api/datasets/patients/acl", json={"allow_roles": ["nope"]})
    assert bad.status_code == 400


def test_dataset_acl_admin_only(client: TestClient) -> None:
    _login(client, "ds", "ds-pw")
    assert client.put("/api/datasets/patients/acl", json={}).status_code == 403
    assert client.get("/api/datasets/patients/acl").status_code == 403


def test_egress_report_json(client: TestClient) -> None:
    _login(client, "dpo", "dpo-pw")
    resp = client.get("/api/reports/egress")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert body["denied_count"] == 1
    assert client.get("/api/reports/egress?since=9999-01-01").json()["total"] == 0


def test_egress_report_forbidden_for_analyst(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    assert client.get("/api/reports/egress").status_code == 403


def test_safety_bias_and_redteam(client: TestClient) -> None:
    _login(client, "ds", "ds-pw")
    resp = client.post(
        "/api/safety/bias",
        json={
            "model_ref": "classifier@1",
            "items": [{"template": "Rate {group} applicant", "groups": ["a", "b"]}],
        },
    )
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json()["passed"], bool)
    resp = client.post("/api/safety/redteam", json={"model_ref": "classifier@1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["passed"] is True
    assert body["total"] == 3


def test_safety_forbidden_for_analyst(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    assert (
        client.post("/api/safety/redteam", json={"model_ref": "m@1"}).status_code == 403
    )
    resp = client.post("/api/safety/bias", json={"model_ref": "m@1", "items": []})
    assert resp.status_code == 403


def test_ropa_only_personal_datasets(client: TestClient) -> None:
    _login(client, "dpo", "dpo-pw")
    resp = client.get("/api/compliance/ropa")
    assert resp.status_code == 200, resp.text
    refs = [a["dataset_ref"] for a in resp.json()["activities"]]
    assert refs == ["patients@1"]


def test_dpia_flow(client: TestClient) -> None:
    _login(client, "dpo", "dpo-pw")
    created = client.post("/api/compliance/dpia", json={"title": "T", "scope": "s"})
    assert created.status_code == 200, created.text
    dpia = created.json()
    assert dpia["status"] == "draft"
    assert dpia["assessor"] == "dpo"
    did = dpia["dpia_id"]

    assert [d["dpia_id"] for d in client.get("/api/compliance/dpia").json()] == [did]
    assert client.get(f"/api/compliance/dpia/{did}").status_code == 200
    assert client.get("/api/compliance/dpia/nope").status_code == 404

    risk = {
        "description": "r",
        "likelihood": "low",
        "impact": "low",
        "mitigation": "m",
        "residual": "low",
    }
    n = len(dpia["risks"])
    added = client.post(f"/api/compliance/dpia/{did}/risk", json=risk).json()
    assert len(added["risks"]) == n + 1

    # draft -> approved is an invalid jump.
    bad = client.post(f"/api/compliance/dpia/{did}/status", json={"status": "approved"})
    assert bad.status_code == 400
    for status in ("in_review", "approved"):
        resp = client.post(
            f"/api/compliance/dpia/{did}/status", json={"status": status}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == status


def test_compliance_forbidden_for_analyst(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    assert client.get("/api/compliance/ropa").status_code == 403
    assert client.get("/api/compliance/dpia").status_code == 403
    assert client.post("/api/compliance/dpia", json={"title": "x"}).status_code == 403


def test_unauthenticated_is_401(client: TestClient) -> None:
    assert client.get("/api/reports/egress").status_code == 401
