"""Unit tests for per-dataset access rules."""

from __future__ import annotations

import pytest

from gadziriro.access.dataset_acl import (
    DatasetAcl,
    DatasetAclStore,
    check_dataset_access,
)
from gadziriro.auth.base import Principal, Role
from gadziriro.core.errors import AuthError


def _user(uid, roles=(), project_roles=None):
    return Principal(
        user_id=uid,
        username=uid,
        roles=frozenset(roles),
        project_roles=project_roles or {},
    )


def test_no_acl_allows() -> None:
    store = DatasetAclStore()
    check_dataset_access(_user("alice"), "ds", store)  # no raise


def test_allow_role_and_user() -> None:
    store = DatasetAclStore()
    store.set_acl(
        DatasetAcl(
            "ds", allow_roles=frozenset({Role.ANALYST}), allow_users=frozenset({"bob"})
        )
    )
    check_dataset_access(_user("bob"), "ds", store)
    check_dataset_access(_user("ann", roles={Role.ANALYST}), "ds", store)
    with pytest.raises(AuthError):
        check_dataset_access(_user("eve"), "ds", store)


def test_deny_user_wins() -> None:
    store = DatasetAclStore()
    store.set_acl(
        DatasetAcl("ds", allow_users=frozenset({"bob"}), deny_users=frozenset({"bob"}))
    )
    with pytest.raises(AuthError):
        check_dataset_access(_user("bob"), "ds", store)


def test_global_admin_always_allowed() -> None:
    store = DatasetAclStore()
    store.set_acl(DatasetAcl("ds", deny_users=frozenset({"root"})))
    check_dataset_access(_user("root", roles={Role.ADMIN}), "ds", store)


def test_project_scoped_role() -> None:
    store = DatasetAclStore()
    store.set_acl(DatasetAcl("ds", allow_roles=frozenset({Role.DATA_SCIENTIST})))
    p = _user("c", project_roles={"proj": frozenset({Role.DATA_SCIENTIST})})
    check_dataset_access(p, "ds", store, project="proj")
    with pytest.raises(AuthError):
        check_dataset_access(p, "ds", store, project="other")
