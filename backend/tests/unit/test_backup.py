"""Unit tests for the backup/restore/test-restore service (FR-28, FR-42)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.errors import GadziriroError, NotFound
from gadziriro.ops.backup import BackupManifest, BackupService


def _make_data_dir(root: Path) -> Path:
    """Populate a workspace-like data dir with a few files and return it."""
    data = root / "data"
    (data / "audit").mkdir(parents=True)
    (data / "registry" / "models").mkdir(parents=True)
    (data / "settings.json").write_text('{"k": "v"}', encoding="utf-8")
    (data / "audit" / "log.ndjson").write_text("line1\nline2\n", encoding="utf-8")
    (data / "registry" / "models" / "weights.bin").write_bytes(b"\x00\x01\x02\x03" * 64)
    return data


def _service(tmp_path: Path) -> tuple[BackupService, Path]:
    data = _make_data_dir(tmp_path)
    svc = BackupService(data, backup_dir=tmp_path / "backups")
    return svc, data


def test_snapshot_creates_archive_and_manifest(tmp_path: Path) -> None:
    svc, _ = _service(tmp_path)
    manifest = svc.snapshot(label="nightly")

    assert isinstance(manifest, BackupManifest)
    assert Path(manifest.archive).is_file()
    assert manifest.size_bytes > 0
    assert manifest.label == "nightly"
    assert manifest.archive_sha256
    # Every source file is recorded with a per-file hash.
    assert set(manifest.files) == {
        "settings.json",
        "audit/log.ndjson",
        "registry/models/weights.bin",
    }
    # The manifest was persisted next to the archive.
    assert (tmp_path / "backups" / f"{manifest.backup_id}.manifest.json").is_file()


def test_restore_reproduces_files_byte_for_byte(tmp_path: Path) -> None:
    svc, data = _service(tmp_path)
    manifest = svc.snapshot()

    dest = tmp_path / "restored"
    svc.restore(manifest.backup_id, dest)

    for rel in manifest.files:
        original = (data / rel).read_bytes()
        restored = (dest / rel).read_bytes()
        assert restored == original


def test_test_restore_returns_true_for_good_backup(tmp_path: Path) -> None:
    svc, _ = _service(tmp_path)
    manifest = svc.snapshot()
    assert svc.test_restore(manifest.backup_id) is True


def test_corrupted_archive_fails_restore_and_test_restore(tmp_path: Path) -> None:
    svc, _ = _service(tmp_path)
    manifest = svc.snapshot()

    # Corrupt the archive on disk.
    Path(manifest.archive).write_bytes(b"not a real tar.gz anymore")

    with pytest.raises(GadziriroError):
        svc.restore(manifest.backup_id, tmp_path / "restored")
    assert svc.test_restore(manifest.backup_id) is False


def test_list_backups_reflects_snapshots(tmp_path: Path) -> None:
    svc, _ = _service(tmp_path)
    assert svc.list_backups() == []

    m1 = svc.snapshot(label="one")
    m2 = svc.snapshot(label="two")

    ids = {m.backup_id for m in svc.list_backups()}
    assert ids == {m1.backup_id, m2.backup_id}
    assert len(svc.list_backups()) == 2


def test_unknown_backup_id_raises_not_found(tmp_path: Path) -> None:
    svc, _ = _service(tmp_path)
    with pytest.raises(NotFound):
        svc.restore("does-not-exist", tmp_path / "restored")
    with pytest.raises(NotFound):
        svc.test_restore("does-not-exist")


def test_manifest_round_trips_through_json(tmp_path: Path) -> None:
    svc, _ = _service(tmp_path)
    manifest = svc.snapshot(label="rt")
    rebuilt = BackupManifest.from_json(manifest.to_json())
    assert rebuilt == manifest
