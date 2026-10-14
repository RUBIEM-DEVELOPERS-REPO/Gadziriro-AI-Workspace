"""FR-35 acceptance: everything is reachable from both the API and the CLI.

FR-35 requires that the workspace's capabilities are driveable headlessly. This
checks two surfaces for the Phase 2 Model Studio features:

* the **CLI** exposes ``model-card``, ``policy effective`` and ``incidents``
  subcommands (built on the same services the gateway wires); and
* the **API** exposes the Model Studio surface (fine-tune, templates, evaluation,
  policy packs) via the FastAPI gateway.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from gadziriro.audit.log import AuditLog
from gadziriro.auth.base import Role
from gadziriro.auth.store import SqlUserStore
from gadziriro.cli.main import main
from gadziriro.core.config import Settings
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.gateway.app import create_app
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry
from gadziriro.runtime.mock import MockRuntimeAdapter
from gadziriro.sessions.manager import SessionManager


# --------------------------------------------------------------------------- #
# CLI surface (FR-35)
# --------------------------------------------------------------------------- #
def _seed_model(data_dir: Path) -> None:
    """Register a model under ``data_dir/objectstore`` (the CLI key layout)."""
    registry = ObjectStoreRegistry(LocalObjectStore(data_dir / "objectstore"))
    registry.add_dataset(
        "patients",
        b"rows",
        sensitivity=SensitivityLabel.PHI,
        source="upload",
        subjects=("subj-1",),
    )
    registry.add_model(
        "triage",
        b"weights",
        lineage=LineageRecord(
            dataset_refs=("patients@1",),
            params={"base_model": "mistral-7b", "epochs": 3},
        ),
    )


def test_cli_model_card_renders(tmp_path, capsys) -> None:
    _seed_model(tmp_path)
    rc = main(
        [
            "model-card",
            "triage",
            "1",
            "--licence",
            "apache-2.0",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Model Card: triage@1" in out
    assert "apache-2.0" in out
    assert "mistral-7b" in out


def test_cli_policy_effective(capsys) -> None:
    rc = main(["policy", "effective", "hipaa", "gdpr"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "effective policy" in out.lower()
    assert "audit_retention_days" in out
    assert "hipaa" in out


def test_cli_incidents_lists(tmp_path, capsys) -> None:
    rc = main(["incidents", "--data-dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "incidents" in out.lower()


# --------------------------------------------------------------------------- #
# API surface (FR-35)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def client(tmp_path) -> TestClient:
    cheap = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    store = SqlUserStore(f"sqlite:///{tmp_path / 'auth.db'}", hasher=cheap)
    store.create_user("ana", "ana-pw", {Role.ANALYST})

    audit = AuditLog(path=tmp_path / "audit.jsonl")
    manager = SessionManager(MockRuntimeAdapter(gpu_count=1), audit=audit)
    object_store = LocalObjectStore(tmp_path / "objectstore")
    registry = ObjectStoreRegistry(object_store)
    registry.add_dataset(
        "patients", b"rows", sensitivity=SensitivityLabel.PHI, source="upload"
    )
    registry.add_model(
        "clf",
        b"weights",
        lineage=LineageRecord(dataset_refs=("patients@1",)),
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


def test_api_exposes_model_studio_surface(client: TestClient) -> None:
    assert (
        client.post(
            "/api/auth/login", json={"username": "ana", "password": "ana-pw"}
        ).status_code
        == 200
    )

    # 1. Fine-tune templates.
    templates = client.get("/api/modelstudio/templates")
    assert templates.status_code == 200
    assert "qlora" in templates.json()["methods"]

    # 2. Launch a fine-tune.
    ft = client.post(
        "/api/modelstudio/finetune",
        json={
            "base_model": "llama-3-8b",
            "dataset_refs": ["patients@1"],
            "output_name": "ft",
        },
    )
    assert ft.status_code == 200
    assert ft.json()["model_ref"].startswith("ft@")

    # 3. Evaluate the seeded model.
    ev = client.post(
        "/api/evaluation/run",
        json={"model_ref": "clf@1", "suite": [{"prompt": "q", "expected": "a"}]},
    )
    assert ev.status_code == 200
    assert "score" in ev.json()

    # 4. Effective compliance policy.
    eff = client.post("/api/policy/packs/effective", json={"enabled": ["hipaa"]})
    assert eff.status_code == 200
    assert eff.json()["settings"]["require_mfa"] is True
