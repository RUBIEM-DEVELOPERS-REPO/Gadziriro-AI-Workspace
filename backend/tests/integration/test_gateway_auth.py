"""Integration tests for the gateway: auth cookie flow, RBAC, sessions, installer."""

from __future__ import annotations

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from gadziriro.audit.log import AuditLog
from gadziriro.auth.base import Role
from gadziriro.auth.store import SqlUserStore
from gadziriro.gateway.app import create_app
from gadziriro.runtime.mock import MockRuntimeAdapter
from gadziriro.sessions.manager import SessionManager


@pytest.fixture()
def client(tmp_path) -> TestClient:
    """A TestClient over an app wired to temp sqlite + mock runtime + temp audit."""
    cheap = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    store = SqlUserStore(f"sqlite:///{tmp_path / 'auth.db'}", hasher=cheap)
    store.create_user("admin", "admin-pw", {Role.ADMIN})
    store.create_user("ana", "ana-pw", {Role.ANALYST})

    audit = AuditLog(path=tmp_path / "audit.jsonl")
    manager = SessionManager(MockRuntimeAdapter(gpu_count=1), audit=audit)
    app = create_app(user_store=store, session_manager=manager, audit=audit)
    return TestClient(app)


def _login(client: TestClient, username: str, password: str):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


def test_protected_route_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_login_sets_cookie_and_me_returns_user(client: TestClient) -> None:
    resp = _login(client, "ana", "ana-pw")
    assert resp.status_code == 200
    assert "gadz_session" in resp.cookies or "gadz_session" in client.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == "ana"
    assert body["roles"] == ["analyst"]


def test_bad_password_is_401(client: TestClient) -> None:
    assert _login(client, "ana", "wrong").status_code == 401


def test_non_admin_cannot_verify_audit(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    assert client.get("/api/audit/verify").status_code == 403


def test_admin_can_verify_audit(client: TestClient) -> None:
    _login(client, "admin", "admin-pw")
    resp = client.get("/api/audit/verify")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_session_crud_through_api(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")

    created = client.post("/api/sessions", json={"session_id": "s1"})
    assert created.status_code == 200
    assert created.json()["session_id"] == "s1"
    assert created.json()["allow_egress"] is False

    listed = client.get("/api/sessions")
    assert listed.status_code == 200
    assert [s["session_id"] for s in listed.json()] == ["s1"]

    got = client.get("/api/sessions/s1")
    assert got.status_code == 200

    ran = client.post("/api/sessions/s1/run-cell", json={"code": "1 + 1"})
    assert ran.status_code == 200
    assert ran.json()["output"] == "2"

    stopped = client.post("/api/sessions/s1/stop")
    assert stopped.status_code == 200
    assert client.get("/api/sessions").json() == []


def test_get_unknown_session_is_404(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    assert client.get("/api/sessions/nope").status_code == 404


def test_installer_hardware_returns_report(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    resp = client.get("/api/installer/hardware")
    assert resp.status_code == 200
    body = resp.json()
    assert "cpu_count" in body
    assert "supported_methods" in body
