"""Local-account authentication routes (FR-16a).

``POST /api/auth/login`` verifies credentials against the user store, issues a
signed session JWT in an httponly cookie, and audits the attempt;
``POST /api/auth/logout`` clears the cookie; ``GET /api/auth/me`` returns the
current principal. Every login (success and failure) and every logout is
written to the tamper-evident audit log — the password is never logged.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from ...audit.base import AuditEvent, AuditSink
from ...auth.base import Principal
from ...auth.store import SqlUserStore
from ...core.errors import AuthError
from ..deps import (
    COOKIE_NAME,
    get_audit,
    get_current_principal,
    get_user_store,
    issue_token,
)
from ..registry import register_router
from ..schemas import LoginRequest, PrincipalOut

router = APIRouter(tags=["auth"])


def _to_out(principal: Principal) -> PrincipalOut:
    """Project a :class:`Principal` onto the wire schema."""
    return PrincipalOut(
        user_id=principal.user_id,
        username=principal.username,
        roles=sorted(role.value for role in principal.roles),
    )


@router.post("/login", response_model=PrincipalOut)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    store: Annotated[SqlUserStore, Depends(get_user_store)],
    audit: Annotated[AuditSink, Depends(get_audit)],
) -> PrincipalOut:
    """Authenticate a local account and set the session cookie.

    :raises AuthError: on bad credentials (mapped to HTTP 401).
    """
    client = request.client.host if request.client else "unknown"
    principal = store.authenticate(body.username, body.password)
    if principal is None:
        audit.append(
            AuditEvent(
                actor=body.username,
                action="auth.login.failed",
                target=body.username,
                reason="invalid credentials",
                level="security",
                meta={"client": client},
            )
        )
        raise AuthError("invalid username or password")

    token = issue_token(principal)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    audit.append(
        AuditEvent(
            actor=principal.username,
            action="auth.login",
            target=principal.user_id,
            reason="ok",
            level="security",
            meta={"client": client},
        )
    )
    return _to_out(principal)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    audit: Annotated[AuditSink, Depends(get_audit)],
) -> dict[str, bool]:
    """Clear the session cookie and audit the logout."""
    actor = "anonymous"
    token = request.cookies.get(COOKIE_NAME)
    if token:
        try:
            actor = get_current_principal(request).username
        except AuthError:
            actor = "anonymous"
    response.delete_cookie(key=COOKIE_NAME, path="/")
    audit.append(
        AuditEvent(
            actor=actor,
            action="auth.logout",
            target=actor,
            reason="ok",
            level="security",
        )
    )
    return {"ok": True}


@router.get("/me", response_model=PrincipalOut)
def me(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> PrincipalOut:
    """Return the authenticated principal.

    :raises AuthError: if not authenticated (mapped to HTTP 401).
    """
    return _to_out(principal)


register_router("/api/auth", router)
