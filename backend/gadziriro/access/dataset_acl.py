"""Per-dataset access rules (FR-18b).

Optional, additive rules on top of project RBAC: a dataset with no ACL falls back to
project access (so this never tightens unless an admin sets a rule), but once an ACL
exists only the listed roles/users may touch that dataset. ``deny_users`` always wins
and a global ADMIN is always allowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..auth.base import Principal, Role
from ..core.errors import AuthError


@dataclass(frozen=True)
class DatasetAcl:
    dataset_name: str
    allow_roles: frozenset[Role] = field(default_factory=frozenset)
    allow_users: frozenset[str] = field(default_factory=frozenset)
    deny_users: frozenset[str] = field(default_factory=frozenset)


class DatasetAclStore:
    """In-memory per-dataset ACL store."""

    def __init__(self) -> None:
        self._acls: dict[str, DatasetAcl] = {}

    def set_acl(self, acl: DatasetAcl) -> None:
        self._acls[acl.dataset_name] = acl

    def get_acl(self, dataset_name: str) -> Optional[DatasetAcl]:
        return self._acls.get(dataset_name)


def check_dataset_access(
    principal: Principal,
    dataset_name: str,
    acl_store: DatasetAclStore,
    *,
    project: Optional[str] = None,
) -> None:
    """Raise AuthError if ``principal`` may not access ``dataset_name``.

    No ACL -> allowed (project RBAC governs elsewhere). deny_users always wins.
    A global ADMIN is always allowed.
    """
    if principal.has_role(Role.ADMIN):
        return
    acl = acl_store.get_acl(dataset_name)
    if acl is None:
        return  # optional rules: absence means "no extra restriction"
    if principal.user_id in acl.deny_users:
        raise AuthError(f"user {principal.user_id} is denied dataset {dataset_name}")
    if principal.user_id in acl.allow_users:
        return
    if any(principal.has_role(r, project) for r in acl.allow_roles):
        return
    raise AuthError(f"user {principal.user_id} lacks access to dataset {dataset_name}")
