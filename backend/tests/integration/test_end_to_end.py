"""End-to-end Phase-0 happy path over the gateway (all mock-backed).

Seeds an admin, logs in, creates a sealed session, runs a cell, lists and stops
it, then verifies the audit chain — exercising the full wiring the CLI and UI
depend on, with a temp-sqlite user store, a :class:`MockRuntimeAdapter`-backed
:class:`SessionManager`, and a ``tmp_path`` :class:`AuditLog`.
"""

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
    """A TestClient over temp sqlite + mock runtime + temp audit."""
    cheap = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    store = SqlUserStore(f"sqlite:///{tmp_path / 'auth.db'}", hasher=cheap)
    store.create_user("admin", "admin-pw", {Role.ADMIN})

    audit = AuditLog(path=tmp_path / "audit.jsonl")
    manager = SessionManager(MockRuntimeAdapter(gpu_count=1), audit=audit)
    app = create_app(user_store=store, session_manager=manager, audit=audit)
    return TestClient(app)


def test_phase0_happy_path(client: TestClient) -> None:
    # 1. Login sets the session cookie.
    login = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin-pw"}
    )
    assert login.status_code == 200
    assert "gadz_session" in login.cookies or "gadz_session" in client.cookies

    # 2. Create a session — sealed from the network by default (FR-20).
    created = client.post("/api/sessions", json={"session_id": "e2e"})
    assert created.status_code == 200
    body = created.json()
    assert body["session_id"] == "e2e"
    assert body["allow_egress"] is False

    # 3. Run a cell and get its output.
    ran = client.post("/api/sessions/e2e/run-cell", json={"code": "1 + 1"})
    assert ran.status_code == 200
    assert ran.json()["output"] == "2"

    # 4. The session shows up in the listing.
    listed = client.get("/api/sessions")
    assert listed.status_code == 200
    assert [s["session_id"] for s in listed.json()] == ["e2e"]

    # 5. Stop it — listing is empty again.
    stopped = client.post("/api/sessions/e2e/stop")
    assert stopped.status_code == 200
    assert client.get("/api/sessions").json() == []

    # 6. Installer hardware report is available.
    hardware = client.get("/api/installer/hardware")
    assert hardware.status_code == 200
    report = hardware.json()
    assert "cpu_count" in report
    assert "supported_methods" in report

    # 7. The audit chain is intact and recorded the login + session events.
    verify = client.get("/api/audit/verify")
    assert verify.status_code == 200
    result = verify.json()
    assert result["ok"] is True
    assert result["count"] > 0
