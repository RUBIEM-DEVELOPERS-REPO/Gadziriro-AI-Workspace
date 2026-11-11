"""FR-18b acceptance: optional per-dataset rules restrict beyond project RBAC."""

from __future__ import annotations

import pytest

from gadziriro.access.dataset_acl import (
    DatasetAcl,
    DatasetAclStore,
    check_dataset_access,
)
from gadziriro.auth.base import Principal, Role
from gadziriro.core.errors import AuthError


def test_per_dataset_rules_override_project_access() -> None:
    store = DatasetAclStore()
    # Two analysts on the same project; a per-dataset rule admits only one.
    alice = Principal("alice", "alice", project_roles={"p": frozenset({Role.ANALYST})})
    bob = Principal("bob", "bob", project_roles={"p": frozenset({Role.ANALYST})})

    # Before any ACL: both have project access to the dataset.
    check_dataset_access(alice, "payroll", store, project="p")
    check_dataset_access(bob, "payroll", store, project="p")

    # Admin adds a per-dataset rule limiting it to alice only.
    store.set_acl(DatasetAcl("payroll", allow_users=frozenset({"alice"})))
    check_dataset_access(alice, "payroll", store, project="p")
    with pytest.raises(AuthError):
        check_dataset_access(bob, "payroll", store, project="p")
