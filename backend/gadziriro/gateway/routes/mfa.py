"""TOTP multi-factor routes (FR-17).

``POST /api/mfa/enroll`` mints a fresh TOTP secret for the caller and returns it
with an ``otpauth://`` provisioning URI (for QR enrolment);
``POST /api/mfa/verify`` checks a code against a supplied secret. Both routes
require an authenticated principal.

Phase 0/1: the secret is returned to the client to store (the enrolment seam);
binding it to the user record is Phase 2. This module only provides the second
factor's generation and verification — session lifetime (auto-logout, FR-17)
remains the gateway JWT's responsibility.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...auth import mfa
from ...auth.base import Principal
from ..deps import get_current_principal
from ..registry import register_router

router = APIRouter(tags=["mfa"])


class EnrollOut(BaseModel):
    """Enrolment response: the shared secret and its provisioning URI."""

    secret: str
    provisioning_uri: str


class VerifyIn(BaseModel):
    """Body for verifying a TOTP code against a secret."""

    secret: str
    code: str


@router.post("/enroll", response_model=EnrollOut)
def enroll(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> EnrollOut:
    """Mint a fresh TOTP secret + provisioning URI for the caller (FR-17)."""
    secret = mfa.generate_secret()
    return EnrollOut(
        secret=secret,
        provisioning_uri=mfa.provisioning_uri(secret, principal.username),
    )


@router.post("/verify")
def verify(
    body: VerifyIn,
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, bool]:
    """Verify a TOTP ``code`` against ``secret`` (FR-17)."""
    return {"ok": mfa.verify(body.secret, body.code)}


register_router("/api/mfa", router)
