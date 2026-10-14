"""Per-project role-based access control (FR-18a).

Pure functions over the :class:`~gadziriro.auth.base.Principal` contract. A
principal may hold *global* roles (``Principal.roles``) that apply everywhere,
and *per-project* roles (``Principal.project_roles``) scoped to one project.

Access to a project resource is granted when the principal holds the required
role for that project (globally or on that project), or when the principal is a
*global* ``ADMIN`` (the workspace administrator, who can reach every project).
"""

from __future__ import annotations

from ..core.errors import AuthError
from .base import Principal, Role


def is_global_admin(principal: Principal) -> bool:
    """Return ``True`` if the principal is a workspace-wide :class:`Role.ADMIN`."""
    return Role.ADMIN in principal.roles


def effective_roles(principal: Principal, project: str) -> frozenset[Role]:
    """Resolve the principal's effective roles *for a given project*.

    This merges the principal's global roles with the roles granted on
    ``project``. A global ``ADMIN`` additionally implies every role for that
    project, so admin-gated checks resolve without enumerating each role.
    """
    merged = set(principal.roles) | set(
        principal.project_roles.get(project, frozenset())
    )
    if is_global_admin(principal):
        merged |= set(Role)
    return frozenset(merged)


def require_project_role(principal: Principal, project: str, required: Role) -> bool:
    """Return whether ``principal`` satisfies ``required`` on ``project``.

    True if the principal has the role (globally or on the project) or is a
    global admin. Does not raise — use :func:`check_access` to enforce.
    """
    return is_global_admin(principal) or principal.has_role(required, project)


def check_access(principal: Principal, project: str, required: Role) -> None:
    """Enforce that ``principal`` may act with ``required`` role on ``project``.

    :raises AuthError: if the principal lacks the required role on the project
        and is not a global admin.
    """
    if require_project_role(principal, project, required):
        return
    raise AuthError(
        f"user {principal.username!r} lacks role {required.value!r} "
        f"on project {project!r}"
    )
