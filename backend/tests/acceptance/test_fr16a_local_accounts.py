"""FR-16a acceptance (exit-gate): local accounts, no SSO.

A local account can be created and then can log in with the correct password and
is refused with the wrong one. Both the success and the failure are written to
the tamper-evident audit log, and the chain still verifies afterwards.
"""

from __future__ import annotations

from pathlib import Path

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from gadziriro.audit.log import AuditLog
from gadziriro.auth.base import Role
from gadziriro.auth.store import SqlUserStore
from gadziriro.gateway.app import create_app
from gadziriro.runtime.mock import MockRuntimeAdapter
from gadziriro.sessions.manager import SessionManager


def _build(tmp_path: Path) -> tuple[TestClient, AuditLog]:
    cheap = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    store = SqlUserStore(f"sqlite:///{tmp_path / 'auth.db'}", hasher=cheap)
    # A LOCAL account — created directly against the store, no SSO/IdP involved.
    store.create_user("local-user", "right-pw", {Role.ANALYST})

    audit = AuditLog(path=tmp_path / "audit.jsonl")
    manager = SessionManager(MockRuntimeAdapter(gpu_count=1), audit=audit)
    app = create_app(user_store=store, session_manager=manager, audit=audit)
    return TestClient(app), audit


def test_fr16a_local_account_login_and_refusal(tmp_path: Path) -> None:
    client, audit = _build(tmp_path)

    # Correct password -> authenticated.
    ok = client.post(
        "/api/auth/login",
        json={"username": "local-user", "password": "right-pw"},
    )
    assert ok.status_code == 200
    assert ok.json()["username"] == "local-user"

    # Wrong password -> refused.
    bad = client.post(
        "/api/auth/login",
        json={"username": "local-user", "password": "WRONG"},
    )
    assert bad.status_code == 401

    # Both outcomes are in the audit log...
    actions = [
        rec["action"]
        for rec in (
            __import__("json").loads(line)
            for line in Path(audit.path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    ]
    assert "auth.login" in actions
    assert "auth.login.failed" in actions

    # ...and the chain still verifies from a fresh reader.
    result = AuditLog(path=audit.path).verify()
    assert result.ok is True
    assert result.broken_at is None
