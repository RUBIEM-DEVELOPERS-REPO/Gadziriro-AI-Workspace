"""Authentication & authorization.

Phase 0: local accounts (FR-16a) with argon2 password hashing, plus an
RBAC-per-project skeleton (FR-18a). SSO/MFA arrive in Phase 1 (FR-16b, FR-17).
Contract in `base.py`; concrete store + password hashing in the implementation.
"""

from .base import Principal, Role, UserStore

__all__ = ["Principal", "Role", "UserStore"]
