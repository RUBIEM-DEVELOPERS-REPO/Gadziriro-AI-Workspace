"""Operational tooling: backup, restore, and automatic test-restore (FR-28, FR-42).

The backup service snapshots the workspace state under ``data_dir`` (settings,
registry, object store, audit) into a single verifiable archive and can restore
it, test-restore it, and list what exists -- all without any third-party
dependency (stdlib ``tarfile``/``hashlib`` only).
"""

from __future__ import annotations

from .backup import BackupManifest, BackupService

__all__ = ["BackupManifest", "BackupService"]
