"""Backup, restore, and automatic test-restore of the workspace (FR-28, FR-42).

A *backup* is a single compressed archive (``tar.gz``) of everything under the
workspace ``data_dir`` -- settings, the versioned registry, the object store,
and the audit log -- accompanied by a JSON *manifest* that records, for every
file, its SHA-256, plus an archive-level SHA-256, the byte size, and a label.

Integrity is checked in two independent ways so a corrupt or truncated backup is
never silently trusted (FR-42):

* **Archive-level** -- :meth:`BackupService.restore` re-hashes the archive bytes
  and compares them to the manifest *before* extracting a single byte, so a
  corrupted archive raises :class:`~gadziriro.core.errors.GadziriroError` rather
  than scattering bad files onto disk.
* **Per-file** -- :meth:`BackupService.test_restore` restores into a throwaway
  temporary directory and re-hashes every extracted file against the manifest.
  This is the "backups are checked and test-restored automatically" guarantee.

The module is deliberately dependency-free (stdlib only) and never touches the
network (privacy default).
"""

from __future__ import annotations

import hashlib
import json
import tarfile
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..core.errors import GadziriroError, NotFound

_ARCHIVE_SUFFIX = ".tar.gz"
_MANIFEST_SUFFIX = ".manifest.json"
_READ_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class BackupManifest:
    """Describes one backup: what it is and how to verify it.

    Attributes:
        backup_id: Unique identifier (also the archive/manifest file stem).
        created_at: UTC timestamp (ISO-8601) when the snapshot was taken.
        archive: Absolute path to the ``tar.gz`` archive on disk.
        archive_sha256: SHA-256 of the whole archive file (corruption guard).
        files: Mapping of archive member path -> SHA-256 of that file's bytes.
        size_bytes: Size of the archive file in bytes.
        label: Optional human-supplied label for the backup.
    """

    backup_id: str
    created_at: str
    archive: str
    archive_sha256: str
    files: dict[str, str] = field(default_factory=dict)
    size_bytes: int = 0
    label: str = ""

    def to_json(self) -> str:
        """Serialise this manifest to indented JSON text."""
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "BackupManifest":
        """Rebuild a manifest from its JSON text."""
        data = json.loads(text)
        return cls(
            backup_id=data["backup_id"],
            created_at=data["created_at"],
            archive=data["archive"],
            archive_sha256=data["archive_sha256"],
            files=dict(data.get("files", {})),
            size_bytes=int(data.get("size_bytes", 0)),
            label=data.get("label", ""),
        )


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 (hex) of a file, read in chunks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_READ_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_all(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract ``tar`` into ``dest`` using the safe data filter when available.

    Python 3.12 (backported to 3.11.4) added ``filter="data"`` to defend against
    path traversal in archive members; we use it when present and fall back
    gracefully on older interpreters.
    """
    try:
        tar.extractall(dest, filter="data")  # type: ignore[call-arg]
    except TypeError:
        tar.extractall(dest)


class BackupService:
    """Snapshot, restore, and test-restore the workspace state (FR-28, FR-42)."""

    def __init__(self, data_dir: Path, *, backup_dir: Path) -> None:
        """Create a service over ``data_dir`` writing archives to ``backup_dir``.

        Args:
            data_dir: The workspace state directory to snapshot / restore from.
            backup_dir: Where archives and manifests are stored; created if new.
        """
        self.data_dir = Path(data_dir)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    # -- paths ---------------------------------------------------------------

    def _archive_path(self, backup_id: str) -> Path:
        return self.backup_dir / f"{backup_id}{_ARCHIVE_SUFFIX}"

    def _manifest_path(self, backup_id: str) -> Path:
        return self.backup_dir / f"{backup_id}{_MANIFEST_SUFFIX}"

    # -- snapshot ------------------------------------------------------------

    def snapshot(self, *, label: str = "") -> BackupManifest:
        """Create a consistent archive of ``data_dir`` and its manifest.

        Every regular file under ``data_dir`` is added to a single ``tar.gz``
        archive under a stable POSIX arcname (its path relative to
        ``data_dir``). Per-file and archive-level SHA-256 digests are recorded
        in the returned (and persisted) :class:`BackupManifest`.

        Args:
            label: Optional human-readable label stored on the manifest.

        Returns:
            The persisted :class:`BackupManifest`.
        """
        created_at = datetime.now(timezone.utc)
        backup_id = f"{created_at.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
        archive_path = self._archive_path(backup_id)

        files: dict[str, str] = {}
        members = sorted(p for p in self.data_dir.rglob("*") if p.is_file())
        with tarfile.open(archive_path, "w:gz") as tar:
            for path in members:
                arcname = path.relative_to(self.data_dir).as_posix()
                files[arcname] = _sha256_file(path)
                tar.add(path, arcname=arcname)

        manifest = BackupManifest(
            backup_id=backup_id,
            created_at=created_at.isoformat(),
            archive=str(archive_path.resolve()),
            archive_sha256=_sha256_file(archive_path),
            files=files,
            size_bytes=archive_path.stat().st_size,
            label=label,
        )
        self._manifest_path(backup_id).write_text(manifest.to_json(), encoding="utf-8")
        return manifest

    # -- lookup --------------------------------------------------------------

    def _load_manifest(self, backup_id: str) -> BackupManifest:
        path = self._manifest_path(backup_id)
        if not path.is_file():
            raise NotFound(f"unknown backup_id: {backup_id}")
        return BackupManifest.from_json(path.read_text(encoding="utf-8"))

    def list_backups(self) -> list[BackupManifest]:
        """Return all known backups, newest first (by ``created_at``)."""
        out: list[BackupManifest] = []
        for mp in self.backup_dir.glob(f"*{_MANIFEST_SUFFIX}"):
            out.append(BackupManifest.from_json(mp.read_text(encoding="utf-8")))
        return sorted(out, key=lambda m: m.created_at, reverse=True)

    # -- restore -------------------------------------------------------------

    def _verify_archive(self, manifest: BackupManifest) -> Path:
        """Verify the archive exists and matches its recorded SHA-256.

        Raises:
            GadziriroError: if the archive is missing or its hash differs.
        """
        archive_path = self._archive_path(manifest.backup_id)
        if not archive_path.is_file():
            raise GadziriroError(f"backup archive missing: {archive_path}")
        actual = _sha256_file(archive_path)
        if actual != manifest.archive_sha256:
            raise GadziriroError(
                f"backup archive corrupted: {manifest.backup_id} "
                f"(expected {manifest.archive_sha256}, got {actual})"
            )
        return archive_path

    def restore(self, backup_id: str, dest: Path) -> None:
        """Verify and extract a backup's archive into ``dest``.

        The archive's SHA-256 is checked against the manifest *before* any file
        is written, so corruption is caught up front.

        Args:
            backup_id: The backup to restore.
            dest: Target directory (created if missing).

        Raises:
            NotFound: if ``backup_id`` is unknown.
            GadziriroError: if the archive is missing or corrupted.
        """
        manifest = self._load_manifest(backup_id)
        archive_path = self._verify_archive(manifest)
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as tar:
            _extract_all(tar, dest)

    def test_restore(self, backup_id: str) -> bool:
        """Automatically restore to a temp dir and verify every file (FR-42).

        Restores into a throwaway temporary directory and compares the SHA-256
        of every extracted file against the manifest. Any archive corruption or
        per-file mismatch makes this return ``False`` rather than raise, so a
        caller can poll it as a health check.

        Args:
            backup_id: The backup to verify.

        Returns:
            ``True`` iff the archive and every file verified; else ``False``.

        Raises:
            NotFound: if ``backup_id`` is unknown.
        """
        manifest = self._load_manifest(backup_id)
        with tempfile.TemporaryDirectory(prefix="gadziriro-testrestore-") as tmp:
            dest = Path(tmp)
            try:
                self.restore(backup_id, dest)
            except GadziriroError:
                return False
            for arcname, expected in manifest.files.items():
                extracted = dest / arcname
                if not extracted.is_file():
                    return False
                if _sha256_file(extracted) != expected:
                    return False
        return True
