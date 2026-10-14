"""Package/model mirror routes (FR-29) — admin-only, offline mirror.

``GET /api/mirror/packages`` lists the ``(name, version)`` pairs currently
mirrored; ``POST /api/mirror/packages`` scans and stores a package (the scanner
raises :class:`~gadziriro.core.errors.PolicyDenied`, mapped to HTTP 403, if the
artifact is blocked). Both routes are restricted to :data:`Role.ADMIN`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...auth.base import Principal, Role
from ...mirror.store import ObjectStoreMirror
from ..deps import get_mirror, require_role
from ..registry import register_router

router = APIRouter(tags=["mirror"])


class AddPackageIn(BaseModel):
    """Body for mirroring a package (content carried as UTF-8 text)."""

    name: str
    version: str
    content: str = ""


@router.get("/packages")
def list_packages(
    mirror: Annotated[ObjectStoreMirror, Depends(get_mirror)],
    _: Annotated[Principal, Depends(require_role(Role.ADMIN))],
) -> list[dict[str, str]]:
    """List the mirrored packages as ``{name, version}`` records."""
    return [
        {"name": name, "version": version} for name, version in mirror.list_packages()
    ]


@router.post("/packages")
def add_package(
    body: AddPackageIn,
    mirror: Annotated[ObjectStoreMirror, Depends(get_mirror)],
    _: Annotated[Principal, Depends(require_role(Role.ADMIN))],
) -> dict[str, Any]:
    """Scan and mirror a package; return its stored meta record.

    :raises PolicyDenied: if the scanner blocks the artifact (HTTP 403).
    """
    return mirror.add_package(body.name, body.version, body.content.encode("utf-8"))


register_router("/api/mirror", router)
