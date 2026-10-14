"""Backup routes (FR-28, FR-42) — admin-only snapshot / restore.

``GET /api/backups`` lists known backups; ``POST /api/backups`` takes a new
snapshot of the workspace state directory; ``POST /api/backups/{id}/test-restore``
restores the backup into a throwaway temp dir and verifies every file (a health
check that never mutates live state). All routes are restricted to
:data:`Role.ADMIN`.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...auth.base import Principal, Role
from ...ops.backup import BackupManifest, BackupService
from ..deps import get_backup_service, require_role
from ..registry import register_router

router = APIRouter(tags=["backup"])


class SnapshotIn(BaseModel):
    """Body for taking a snapshot (optional human label)."""

    label: str = ""


def _manifest_to_dict(manifest: BackupManifest) -> dict[str, Any]:
    """Project a :class:`BackupManifest` onto a JSON-serialisable dict."""
    return asdict(manifest)


@router.get("")
def list_backups(
    service: Annotated[BackupService, Depends(get_backup_service)],
    _: Annotated[Principal, Depends(require_role(Role.ADMIN))],
) -> list[dict[str, Any]]:
    """List known backups, newest first."""
    return [_manifest_to_dict(m) for m in service.list_backups()]


@router.post("")
def snapshot(
    body: SnapshotIn,
    service: Annotated[BackupService, Depends(get_backup_service)],
    _: Annotated[Principal, Depends(require_role(Role.ADMIN))],
) -> dict[str, Any]:
    """Take a new snapshot and return its manifest."""
    return _manifest_to_dict(service.snapshot(label=body.label))


@router.post("/{backup_id}/test-restore")
def test_restore(
    backup_id: str,
    service: Annotated[BackupService, Depends(get_backup_service)],
    _: Annotated[Principal, Depends(require_role(Role.ADMIN))],
) -> dict[str, bool]:
    """Restore the backup into a temp dir and verify it (FR-42).

    :raises NotFound: if the backup id is unknown (mapped to HTTP 404).
    """
    return {"ok": service.test_restore(backup_id)}


register_router("/api/backups", router)
