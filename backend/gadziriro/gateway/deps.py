"""Gateway dependencies: JWT session cookie, principal resolution, RBAC.

The session is a stateless HS256 JWT carried in an httponly cookie
(:data:`COOKIE_NAME`). :func:`get_current_principal` decodes it into a
:class:`Principal`; :func:`require_role` builds a dependency that enforces a
role. Shared services (user store, session manager, audit sink) are read off
``app.state`` so tests can inject fakes via :func:`create_app`.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Callable

from fastapi import Request
from jose import JWTError, jwt

from ..audit.base import AuditSink
from ..auth.base import Principal, Role
from ..auth.store import SqlUserStore
from ..core.errors import AuthError, PolicyDenied
from ..sessions.manager import SessionManager

COOKIE_NAME = "gadz_session"
JWT_ALGORITHM = "HS256"
# A per-process fallback so dev works without configuration. Set
# GADZIRIRO_SECRET in any real deployment (tokens do not survive a restart
# otherwise).
_DEV_SECRET = secrets.token_urlsafe(32)


def get_secret() -> str:
    """Return the JWT signing secret (env ``GADZIRIRO_SECRET`` or a dev secret)."""
    return os.environ.get("GADZIRIRO_SECRET", _DEV_SECRET)


def issue_token(principal: Principal) -> str:
    """Encode ``principal`` into a signed session JWT."""
    claims: dict[str, Any] = {
        "sub": principal.user_id,
        "username": principal.username,
        "roles": [role.value for role in principal.roles],
    }
    return jwt.encode(claims, get_secret(), algorithm=JWT_ALGORITHM)


def principal_from_token(token: str) -> Principal:
    """Decode a session JWT into a :class:`Principal`.

    :raises AuthError: if the token is missing, malformed, or badly signed.
    """
    try:
        claims = jwt.decode(token, get_secret(), algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise AuthError("invalid session token") from exc
    try:
        roles = frozenset(Role(value) for value in claims.get("roles", []))
        return Principal(
            user_id=str(claims["sub"]),
            username=str(claims["username"]),
            roles=roles,
        )
    except (KeyError, ValueError) as exc:
        raise AuthError("malformed session token") from exc


def get_current_principal(request: Request) -> Principal:
    """Resolve the authenticated :class:`Principal` from the session cookie.

    :raises AuthError: if no valid session cookie is present.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise AuthError("not authenticated")
    return principal_from_token(token)


def require_role(role: Role) -> Callable[[Request], Principal]:
    """Build a dependency that requires ``role`` on the current principal.

    :raises PolicyDenied: if the authenticated principal lacks ``role``.
    """

    def _dependency(request: Request) -> Principal:
        principal = get_current_principal(request)
        if not principal.has_role(role):
            raise PolicyDenied(f"requires role: {role.value}")
        return principal

    return _dependency


def get_user_store(request: Request) -> SqlUserStore:
    """Return the user store wired onto ``app.state``."""
    return request.app.state.user_store


def get_session_manager(request: Request) -> SessionManager:
    """Return the session manager wired onto ``app.state``."""
    return request.app.state.session_manager


def get_audit(request: Request) -> AuditSink:
    """Return the audit sink wired onto ``app.state``."""
    return request.app.state.audit
