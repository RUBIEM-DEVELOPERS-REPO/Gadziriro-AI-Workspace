"""Per-dataset access-rule routes (FR-18b) — admin only.

* ``PUT /api/datasets/{name}/acl`` — set the dataset's ACL.
* ``GET /api/datasets/{name}/acl`` — read it (404 if none set).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...access.dataset_acl import DatasetAcl, DatasetAclStore
from ...auth.base import Principal, Role
from ...core.errors import GadziriroError, NotFound
from ..deps import get_dataset_acl_store, require_role
from ..registry import register_router

router = APIRouter(tags=["dataset-acl"])

_require_admin = require_role(Role.ADMIN)


class DatasetAclIn(BaseModel):
    """Body for setting a dataset ACL."""

    allow_roles: list[str] = Field(default_factory=list)
    allow_users: list[str] = Field(default_factory=list)
    deny_users: list[str] = Field(default_factory=list)


def _to_dict(acl: DatasetAcl) -> dict[str, Any]:
    return {
        "dataset_name": acl.dataset_name,
        "allow_roles": sorted(r.value for r in acl.allow_roles),
        "allow_users": sorted(acl.allow_users),
        "deny_users": sorted(acl.deny_users),
    }


@router.put("/{name}/acl")
def put_acl(
    name: str,
    body: DatasetAclIn,
    store: Annotated[DatasetAclStore, Depends(get_dataset_acl_store)],
    _: Annotated[Principal, Depends(_require_admin)],
) -> dict[str, Any]:
    """Set (replace) the ACL for a dataset (400 on an unknown role)."""
    try:
        roles = frozenset(Role(r) for r in body.allow_roles)
    except ValueError as exc:
        raise GadziriroError(f"unknown role: {exc}") from exc
    acl = DatasetAcl(
        dataset_name=name,
        allow_roles=roles,
        allow_users=frozenset(body.allow_users),
        deny_users=frozenset(body.deny_users),
    )
    store.set_acl(acl)
    return _to_dict(acl)


@router.get("/{name}/acl")
def get_acl(
    name: str,
    store: Annotated[DatasetAclStore, Depends(get_dataset_acl_store)],
    _: Annotated[Principal, Depends(_require_admin)],
) -> dict[str, Any]:
    """Return a dataset's ACL (404 if none is set)."""
    acl = store.get_acl(name)
    if acl is None:
        raise NotFound(f"no ACL set for dataset: {name}")
    return _to_dict(acl)


register_router("/api/datasets", router)
