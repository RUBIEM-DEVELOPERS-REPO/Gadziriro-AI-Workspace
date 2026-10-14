"""Unit tests for per-project RBAC (FR-18a)."""

from __future__ import annotations

import pytest

from gadziriro.auth.base import Principal, Role
from gadziriro.auth.rbac import (
    check_access,
    effective_roles,
    is_global_admin,
    require_project_role,
)
from gadziriro.core.errors import AuthError


def _analyst_on_x() -> Principal:
    return Principal(
        user_id="u1",
        username="ana",
        project_roles={"x": frozenset({Role.ANALYST})},
    )


def _global_admin() -> Principal:
    return Principal(user_id="u0", username="root", roles=frozenset({Role.ADMIN}))


def test_project_role_passes_on_its_project() -> None:
    ana = _analyst_on_x()
    # Does not raise.
    check_access(ana, "x", Role.ANALYST)
    assert require_project_role(ana, "x", Role.ANALYST) is True


def test_project_role_fails_on_other_project() -> None:
    ana = _analyst_on_x()
    assert require_project_role(ana, "y", Role.ANALYST) is False
    with pytest.raises(AuthError):
        check_access(ana, "y", Role.ANALYST)


def test_global_admin_passes_everywhere() -> None:
    admin = _global_admin()
    assert is_global_admin(admin) is True
    check_access(admin, "x", Role.ANALYST)
    check_access(admin, "any-project", Role.DATA_SCIENTIST)
    check_access(admin, "another", Role.COMPLIANCE)


def test_insufficient_role_raises() -> None:
    ana = _analyst_on_x()
    with pytest.raises(AuthError):
        check_access(ana, "x", Role.ADMIN)


def test_effective_roles_merges_global_and_project() -> None:
    p = Principal(
        user_id="u2",
        username="mix",
        roles=frozenset({Role.VIEWER}),
        project_roles={"x": frozenset({Role.ANALYST})},
    )
    eff = effective_roles(p, "x")
    assert Role.VIEWER in eff
    assert Role.ANALYST in eff
    # On a different project, only the global role applies.
    assert effective_roles(p, "y") == frozenset({Role.VIEWER})


def test_effective_roles_admin_implies_all() -> None:
    eff = effective_roles(_global_admin(), "x")
    assert eff == frozenset(Role)
