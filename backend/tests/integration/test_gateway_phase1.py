"""Integration tests for the Phase 1 gateway wiring.

Exercises the newly surfaced services through the FastAPI ``TestClient``:
registry (datasets/models + lineage), job submission, Prometheus ``/metrics``,
admin-only backup snapshot/test-restore (and a non-admin 403), governance DSAR
find/erase, and the TOTP MFA enrol/verify round-trip. Fixture wiring mirrors
``test_gateway_auth`` (temp sqlite user store, mock-runtime session manager, temp
audit log, temp data dir) with a pre-seeded registry.
"""

from __future__ import annotations

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from gadziriro.audit.log import AuditLog
from gadziriro.auth import mfa
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
    store.create_user("dpo", "dpo-pw", {Role.COMPLIANCE})

    audit = AuditLog(path=tmp_path / "audit.jsonl")
    manager = SessionManager(MockRuntimeAdapter(gpu_count=1), audit=audit)

    object_store = LocalObjectStore(tmp_path / "objectstore")
    registry = ObjectStoreRegistry(object_store)
    registry.add_dataset(
        "patients",
        b"rows",
        sensitivity=SensitivityLabel.PERSONAL,
        source="upload",
        subjects=("subj-1",),
    )
    registry.add_model(
        "classifier",
        b"weights",
        lineage=LineageRecord(dataset_refs=("patients@1",), code_ref="abc123"),
        sensitivity=SensitivityLabel.INTERNAL,
    )

    settings = Settings(data_dir=tmp_path / "data")
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


def test_datasets_endpoints_return_registry_contents(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")

    listed = client.get("/api/datasets")
    assert listed.status_code == 200
    names = [d["name"] for d in listed.json()]
    assert "patients" in names

    one = client.get("/api/datasets/patients")
    assert one.status_code == 200
    versions = one.json()["versions"]
    assert versions[0]["sensitivity"] == "personal"
    assert versions[0]["subjects"] == ["subj-1"]


def test_models_endpoints_return_lineage(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")

    listed = client.get("/api/models")
    assert listed.status_code == 200
    assert "classifier" in [m["name"] for m in listed.json()]

    version = client.get("/api/models/classifier/1")
    assert version.status_code == 200
    body = version.json()
    assert body["ref"] == "classifier@1"
    assert body["lineage"]["dataset_refs"] == ["patients@1"]


def test_job_submit_and_list(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")

    submitted = client.post("/api/jobs", json={"command": "echo hi", "project": "demo"})
    assert submitted.status_code == 200
    job_id = submitted.json()["job_id"]
    assert submitted.json()["command"] == ["echo hi"]

    listed = client.get("/api/jobs")
    assert listed.status_code == 200
    assert job_id in [j["job_id"] for j in listed.json()]

    got = client.get(f"/api/jobs/{job_id}")
    assert got.status_code == 200
    assert got.json()["job_id"] == job_id


def test_metrics_endpoint_returns_prometheus_text(client: TestClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "gadziriro_gpus_total" in body
    assert "gadziriro_jobs_running" in body


def test_admin_can_snapshot_and_test_restore_backup(client: TestClient) -> None:
    _login(client, "admin", "admin-pw")

    snap = client.post("/api/backups", json={"label": "nightly"})
    assert snap.status_code == 200
    backup_id = snap.json()["backup_id"]

    listed = client.get("/api/backups")
    assert listed.status_code == 200
    assert backup_id in [b["backup_id"] for b in listed.json()]

    restored = client.post(f"/api/backups/{backup_id}/test-restore")
    assert restored.status_code == 200
    assert restored.json()["ok"] is True


def test_non_admin_is_forbidden_on_admin_routes(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")
    assert client.get("/api/backups").status_code == 403
    assert client.get("/api/mirror/packages").status_code == 403


def test_governance_dsar_find_and_erase(client: TestClient) -> None:
    _login(client, "dpo", "dpo-pw")

    found = client.get("/api/governance/dsar/subj-1")
    assert found.status_code == 200
    assert "classifier@1" in [m["ref"] for m in found.json()["models"]]

    erased = client.post("/api/governance/dsar/subj-1/erase")
    assert erased.status_code == 200
    assert "classifier@1" in erased.json()["flagged"]

    again = client.get("/api/governance/dsar/subj-1")
    flagged = {m["ref"]: m["flagged"] for m in again.json()["models"]}
    assert flagged["classifier@1"] is True


def test_mfa_enroll_and_verify_round_trip(client: TestClient) -> None:
    _login(client, "ana", "ana-pw")

    enrolled = client.post("/api/mfa/enroll")
    assert enrolled.status_code == 200
    secret = enrolled.json()["secret"]
    assert enrolled.json()["provisioning_uri"].startswith("otpauth://totp/")

    code = mfa.totp(secret)
    verified = client.post("/api/mfa/verify", json={"secret": secret, "code": code})
    assert verified.status_code == 200
    assert verified.json()["ok"] is True

    bad = client.post("/api/mfa/verify", json={"secret": secret, "code": "000000"})
    assert bad.json()["ok"] is False
