"""Acceptance: FR-28 backup/restore + FR-42 automatic integrity test-restore.

Scenario: the whole workspace state (settings, registry, object store, audit)
must be backed up to a single archive and faithfully restored, and every backup
must be automatically checked and test-restored so corruption cannot pass
unnoticed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.errors import GadziriroError
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.ops.backup import BackupService


def _seed_workspace(data_dir: Path) -> dict[str, bytes]:
    """Lay down a realistic workspace tree and return expected object bytes."""
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "settings.json").write_text(
        '{"runtime_backend": "mock"}', encoding="utf-8"
    )
    (data_dir / "audit").mkdir(parents=True, exist_ok=True)
    (data_dir / "audit" / "chain.ndjson").write_text(
        "GENESIS\nrecord-1\nrecord-2\n", encoding="utf-8"
    )

    store = LocalObjectStore(data_dir / "objectstore")
    objects = {
        "registry/datasets/sales.parquet": b"PARQUET\x00data" * 100,
        "registry/models/model-v1.bin": bytes(range(256)) * 16,
    }
    for key, value in objects.items():
        store.put(key, value)
    return objects


def test_fr28_full_workspace_backup_and_restore_round_trip(tmp_path: Path) -> None:
    """FR-28: snapshot the workspace and restore it byte-for-byte elsewhere."""
    data_dir = tmp_path / "workspace"
    objects = _seed_workspace(data_dir)

    svc = BackupService(data_dir, backup_dir=tmp_path / "backups")
    manifest = svc.snapshot(label="fr28-acceptance")

    # The backup is a single archive plus a manifest describing it.
    assert Path(manifest.archive).is_file()
    assert svc.list_backups()[0].backup_id == manifest.backup_id

    # Restore into a brand-new location and read the object store back.
    restore_dir = tmp_path / "restored"
    svc.restore(manifest.backup_id, restore_dir)

    restored_store = LocalObjectStore(restore_dir / "objectstore")
    for key, value in objects.items():
        assert restored_store.get(key) == value

    # Non-object-store state is restored too.
    assert (restore_dir / "settings.json").read_text(encoding="utf-8") == (
        data_dir / "settings.json"
    ).read_text(encoding="utf-8")
    assert (restore_dir / "audit" / "chain.ndjson").read_bytes() == (
        data_dir / "audit" / "chain.ndjson"
    ).read_bytes()


def test_fr42_automatic_test_restore_passes_for_good_backup(tmp_path: Path) -> None:
    """FR-42: a freshly taken backup verifies automatically."""
    data_dir = tmp_path / "workspace"
    _seed_workspace(data_dir)
    svc = BackupService(data_dir, backup_dir=tmp_path / "backups")
    manifest = svc.snapshot()

    assert svc.test_restore(manifest.backup_id) is True


def test_fr42_corrupted_backup_is_detected(tmp_path: Path) -> None:
    """FR-42: a corrupted archive is rejected by both restore and test-restore."""
    data_dir = tmp_path / "workspace"
    _seed_workspace(data_dir)
    svc = BackupService(data_dir, backup_dir=tmp_path / "backups")
    manifest = svc.snapshot()

    # Flip bytes in the middle of the archive to simulate bit-rot.
    archive = Path(manifest.archive)
    raw = bytearray(archive.read_bytes())
    mid = len(raw) // 2
    raw[mid] ^= 0xFF
    archive.write_bytes(bytes(raw))

    assert svc.test_restore(manifest.backup_id) is False
    with pytest.raises(GadziriroError):
        svc.restore(manifest.backup_id, tmp_path / "restored")
