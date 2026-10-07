"""Auth contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol


class Role(str, Enum):
    """Phase-0 roles (maps to the §5 stakeholder roles; refined in Phase 1)."""

    ADMIN = "admin"  # workspace administrator
    DATA_SCIENTIST = "data_scientist"
    ANALYST = "analyst"
    COMPLIANCE = "compliance"  # DPO / auditor (read audit, exports, evidence)
    VIEWER = "viewer"


@dataclass(frozen=True)
class Principal:
    """An authenticated user. Roles are per-project (FR-18a)."""

    user_id: str
    username: str
    roles: frozenset[Role] = field(default_factory=frozenset)
    project_roles: dict[str, frozenset[Role]] = field(default_factory=dict)

    def has_role(self, role: Role, project: Optional[str] = None) -> bool:
        if role in self.roles:
            return True
        if project is not None:
            return role in self.project_roles.get(project, frozenset())
        return False


class UserStore(Protocol):
    """Local-account user store contract."""

    def create_user(
        self, username: str, password: str, roles: set[Role]
    ) -> Principal: ...

    def authenticate(self, username: str, password: str) -> Optional[Principal]:
        """Return the Principal on success, None on bad credentials."""
        ...

    def get(self, user_id: str) -> Optional[Principal]: ...
