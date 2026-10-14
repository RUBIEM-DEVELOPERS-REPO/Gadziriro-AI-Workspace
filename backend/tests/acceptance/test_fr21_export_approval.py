"""Acceptance tests for FR-21 — export approval.

FR-21: exporting a PERSONAL/PHI resource requires human approval; the export is
blocked until approved; every step is auditable. A PUBLIC/INTERNAL export is
auto-approved. These tests drive the :class:`~gadziriro.policy.exports.ExportPolicy`
against a real tamper-evident audit log and also exercise the gateway routes
(including the non-admin 403 on the approve action).
"""

from __future__ import annotations

import json

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from gadziriro.audit.log import AuditLog
from gadziriro.auth.base import Role
from gadziriro.auth.store import SqlUserStore
from gadziriro.core.config import Settings
from gadziriro.core.errors import PolicyDenied
from gadziriro.gateway.app import create_app
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.policy.exports import ExportPolicy
from gadziriro.runtime.mock import MockRuntimeAdapter
from gadziriro.sessions.manager import SessionManager


def _audit_actions(audit: AuditLog) -> list[str]:
    """Return the ``action`` of every record in ``audit`` (newest-safe)."""
    lines = audit.path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["action"] for line in lines if line.strip()]


def test_phi_export_requires_approval_then_allowed(tmp_path) -> None:
    """A PHI export is pending + blocked, allowed after approval, fully audited."""
    audit = AuditLog(path=tmp_path / "audit.jsonl")
    policy = ExportPolicy(audit=audit)

    req = policy.request_export("patients@3", SensitivityLabel.PHI, "ana")
    assert req.status == "pending"

    # Attempting the export before approval is blocked.
    with pytest.raises(PolicyDenied):
        policy.assert_export_allowed(req.request_id)

    approved = policy.approve(req.request_id, "admin")
    assert approved.status == "approved"
    assert approved.decided_by == "admin"

    # Now the export is allowed.
    allowed = policy.assert_export_allowed(req.request_id)
    assert allowed.is_allowed

    # Every step is in the audit log and the chain still verifies.
    actions = _audit_actions(audit)
    assert "export.request" in actions
    assert "export.approve" in actions
    assert audit.verify().ok is True


def test_personal_export_can_be_denied(tmp_path) -> None:
    """A PERSONAL export can be denied, which keeps the export blocked."""
    audit = AuditLog(path=tmp_path / "audit.jsonl")
    policy = ExportPolicy(audit=audit)

    req = policy.request_export("notes@1", SensitivityLabel.PERSONAL, "ana")
    assert req.status == "pending"

    denied = policy.deny(req.request_id, "admin", "insufficient justification")
    assert denied.status == "denied"
    assert denied.reason == "insufficient justification"

    with pytest.raises(PolicyDenied):
        policy.assert_export_allowed(req.request_id)

    actions = _audit_actions(audit)
    assert "export.deny" in actions
    assert audit.verify().ok is True


def test_public_and_internal_exports_are_auto_approved(tmp_path) -> None:
    """PUBLIC/INTERNAL exports skip approval and are immediately allowed."""
    audit = AuditLog(path=tmp_path / "audit.jsonl")
    policy = ExportPolicy(audit=audit)

    for label in (SensitivityLabel.PUBLIC, SensitivityLabel.INTERNAL):
        req = policy.request_export("metrics@2", label, "ana")
        assert req.status == "auto-approved"
        assert policy.assert_export_allowed(req.request_id).is_allowed

    assert audit.verify().ok is True


@pytest.fixture()
def client(tmp_path) -> TestClient:
    """A TestClient wired like the gateway integration suite."""
    cheap = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    store = SqlUserStore(f"sqlite:///{tmp_path / 'auth.db'}", hasher=cheap)
    store.create_user("admin", "admin-pw", {Role.ADMIN})
    store.create_user("ana", "ana-pw", {Role.ANALYST})

    audit = AuditLog(path=tmp_path / "audit.jsonl")
    manager = SessionManager(MockRuntimeAdapter(gpu_count=1), audit=audit)
    settings = Settings(data_dir=tmp_path / "data")
    app = create_app(settings, user_store=store, session_manager=manager, audit=audit)
    return TestClient(app)


def _login(client: TestClient, username: str, password: str) -> None:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200


def test_export_approval_flow_through_api(client: TestClient) -> None:
    """Request (pending) -> non-admin approve 403 -> admin approve -> chain ok."""
    _login(client, "ana", "ana-pw")
    created = client.post(
        "/api/exports", json={"resource_ref": "patients@3", "sensitivity": "phi"}
    )
    assert created.status_code == 200
    request_id = created.json()["request_id"]
    assert created.json()["status"] == "pending"

    # A non-admin cannot approve.
    assert client.post(f"/api/exports/{request_id}/approve").status_code == 403

    # An admin approves.
    _login(client, "admin", "admin-pw")
    approved = client.post(f"/api/exports/{request_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    # The chain still verifies after the recorded request + approval.
    verify = client.get("/api/audit/verify")
    assert verify.status_code == 200
    assert verify.json()["ok"] is True


def test_public_export_auto_approved_through_api(client: TestClient) -> None:
    """A PUBLIC export is auto-approved on request."""
    _login(client, "ana", "ana-pw")
    created = client.post(
        "/api/exports", json={"resource_ref": "report@1", "sensitivity": "public"}
    )
    assert created.status_code == 200
    assert created.json()["status"] == "auto-approved"
