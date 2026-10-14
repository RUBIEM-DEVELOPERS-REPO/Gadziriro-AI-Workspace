"""Unit tests for PII-stripped support bundles (FR-40)."""

from __future__ import annotations

from pathlib import Path

from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.ops.support_bundle import build_support_bundle, default_redactor

SECRET_EMAIL = "patient.alice@hospital.example"
RAW_DATASET_BYTES = "ALICE-SSN-123-45-6789-RAW-PHI-PAYLOAD"
SUBJECT_ID = "subject-alice-0001"


def _seed_data_dir(root: Path) -> Path:
    """Create a workspace-like data dir seeded with PII and raw dataset bytes."""
    data = root / "data"
    (data / "audit").mkdir(parents=True)
    (data / "datasets" / "patients" / "1").mkdir(parents=True)
    (data / "personal").mkdir(parents=True)

    # Benign config and a log line carrying an email (must be masked).
    (data / "settings.json").write_text('{"runtime_backend": "mock"}', encoding="utf-8")
    (data / "audit" / "log.jsonl").write_text(
        f'{{"actor": "{SECRET_EMAIL}", "action": "auth.login"}}\n',
        encoding="utf-8",
    )
    # Raw dataset bytes and a personal-labelled file that must NEVER be read.
    (data / "datasets" / "patients" / "1" / "blob").write_text(
        RAW_DATASET_BYTES, encoding="utf-8"
    )
    (data / "personal" / "notes.log").write_text(
        f"PHI note for {SUBJECT_ID}", encoding="utf-8"
    )
    return data


def test_bundle_is_created_and_returns_metadata(tmp_path: Path) -> None:
    data = _seed_data_dir(tmp_path)
    out_store = LocalObjectStore(tmp_path / "out")

    result = build_support_bundle(data_dir=data, out_store=out_store)

    assert out_store.exists(result["bundle_key"])
    assert "created_at" in result
    assert result["redacted_fields_count"] > 0


def test_bundle_contains_no_pii_or_raw_dataset_bytes(tmp_path: Path) -> None:
    data = _seed_data_dir(tmp_path)
    out_store = LocalObjectStore(tmp_path / "out")

    result = build_support_bundle(data_dir=data, out_store=out_store)
    blob = out_store.get(result["bundle_key"]).decode("utf-8")

    # No email, no raw dataset bytes, no PHI note / subject id anywhere.
    assert SECRET_EMAIL not in blob
    assert RAW_DATASET_BYTES not in blob
    assert SUBJECT_ID not in blob
    assert "@hospital.example" not in blob


def test_default_redactor_masks_and_counts() -> None:
    payload = {
        "actor": "someone@example.com",
        "email": "explicit@example.com",
        "note": "nothing sensitive here",
    }
    redacted, count = default_redactor(payload)
    assert count >= 2
    assert "example.com" not in str(redacted["actor"])
    assert redacted["email"] != "explicit@example.com"
    assert redacted["note"] == "nothing sensitive here"


def test_custom_redactor_is_honoured(tmp_path: Path) -> None:
    data = _seed_data_dir(tmp_path)
    out_store = LocalObjectStore(tmp_path / "out")
    calls: list[int] = []

    def noop_redactor(bundle):
        calls.append(1)
        return bundle, 7

    result = build_support_bundle(
        data_dir=data, out_store=out_store, redactor=noop_redactor
    )
    assert calls == [1]
    assert result["redacted_fields_count"] == 7
