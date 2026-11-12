"""Integration tests for the Phase 4 gateway wiring.

Plug-in kit (FR-32) and auditor evidence export (FR-26) through the FastAPI
``TestClient``, with role gating. Fixture mirrors Phase 3.
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
from gadziriro.plugins.kit import sign_plugin
from gadziriro.registry.store import ObjectStoreRegistry
from gadziriro.runtime.mock import MockRuntimeAdapter
from gadziriro.sessions.manager import SessionManager


@pytest.fixture()
def client(tmp_path) -> TestClient:
    cheap = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    store = SqlUserStore(f"sqlite:///{tmp_path / 'auth.db'}", hasher=cheap)
    store.create_user("admin", "admin-pw", {Role.ADMIN})
    store.create_user("ana", "ana-pw", {Role.ANALYST})
    store.create_user("dpo", "dpo-pw", {Role.COMPLIANCE})

    audit = AuditLog(path=tmp_path / "audit.jsonl")
    audit.append(AuditEvent(actor="admin", action="export.approve", target="m@1"))
    manager = SessionManager(MockRuntimeAdapter(gpu_count=1), audit=audit)

    object_store = LocalObjectStore(tmp_path / "objectstore")
    registry = ObjectStoreRegistry(object_store)
    registry.add_dataset(
        "clients", b"rows", sensitivity=SensitivityLabel.PERSONAL, source="crm"
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


def _signed_plugin(client: TestClient, name: str, kind: str, *, key=None) -> dict:
    key = key or client.app.state.plugin_dev_signing_key
    manifest = {
        "name": name,
        "kind": kind,
        "version": "1.0.0",
        "entrypoint": "plugin:main",
        "api_version": "1",
    }
    bundle = sign_plugin(manifest, b"plugin-payload", key)
    return {
        "manifest": bundle.manifest,
        "payload_b64": base64.b64encode(bundle.payload).decode(),
        "sig": bundle.sig,
    }


def test_plugin_install_enable(client: TestClient) -> None:
    _login(client, "admin", "admin-pw")
    body = _signed_plugin(client, "vision-pack", "vision")
    r = client.post("/api/plugins/install", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["installed"] is True

    plugins = client.get("/api/plugins").json()
    assert any(p["name"] == "vision-pack" and p["enabled"] is False for p in plugins)

    r = client.post("/api/plugins/vision-pack/enable")
    assert r.status_code == 200 and r.json()["enabled"] is True


def test_plugin_forged_rejected(client: TestClient) -> None:
    from nacl.signing import SigningKey

    _login(client, "admin", "admin-pw")
    forged = _signed_plugin(client, "evil", "tabular", key=SigningKey.generate())
    assert client.post("/api/plugins/install", json=forged).status_code == 400


def test_plugins_admin_only(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    assert client.get("/api/plugins").status_code == 403


def test_evidence_export_and_list(client: TestClient) -> None:
    _login(client, "dpo", "dpo-pw")
    r = client.post("/api/evidence/export", json={"enabled_packs": ["gdpr"]})
    assert r.status_code == 200, r.text
    manifest = r.json()
    assert manifest["audit_ok"] is True
    assert "sbom" in manifest["sections"]

    listing = client.get("/api/evidence").json()
    assert len(listing) >= 1 and listing[0]["audit_ok"] is True


def test_evidence_requires_role(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    assert client.post("/api/evidence/export", json={}).status_code == 403
