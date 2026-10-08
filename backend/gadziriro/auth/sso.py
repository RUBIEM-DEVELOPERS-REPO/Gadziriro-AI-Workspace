"""OIDC authorization-code SSO client (FR-16b).

A small, dependency-light OpenID Connect *authorization code* client. It is
deliberately split into three pure-ish steps so each is testable offline:

1. :meth:`OidcClient.authorization_url` builds the redirect to the IdP's
   ``/authorize`` endpoint (no network).
2. :meth:`OidcClient.exchange_code` swaps the returned ``code`` for tokens at
   the ``/token`` endpoint. The HTTP call is injectable via ``token_exchanger``
   so tests never touch the network (the default uses :mod:`httpx`).
3. :meth:`OidcClient.principal_from_id_token` decodes the ID token's claims
   into a :class:`~gadziriro.auth.base.Principal`. Verification is injectable
   via ``verifier`` (the default decodes with ``python-jose``); tests pass a
   fake that returns a claims dict.

Keeping every network/crypto seam injectable means the unit tests are offline
and deterministic, while production wiring supplies real HTTP + JWKS
verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlencode

from ..core.errors import AuthError
from .base import Principal, Role

# A callable that performs the token-endpoint POST: (token_endpoint, form_data)
# -> decoded JSON token response. Injected so tests avoid real HTTP.
TokenExchanger = Callable[[str, Mapping[str, str]], Mapping[str, Any]]

# A callable that verifies/decodes an ID token into its claims mapping.
IdTokenVerifier = Callable[[str], Mapping[str, Any]]

# Map common IdP group/role names onto Gadziriro roles. Unknown values are
# ignored (default roles stay empty) rather than guessed.
_ROLE_ALIASES: dict[str, Role] = {
    "admin": Role.ADMIN,
    "administrator": Role.ADMIN,
    "data_scientist": Role.DATA_SCIENTIST,
    "datascientist": Role.DATA_SCIENTIST,
    "data-scientist": Role.DATA_SCIENTIST,
    "analyst": Role.ANALYST,
    "compliance": Role.COMPLIANCE,
    "dpo": Role.COMPLIANCE,
    "auditor": Role.COMPLIANCE,
    "viewer": Role.VIEWER,
}


@dataclass(frozen=True)
class OidcConfig:
    """Static OpenID Connect provider + client configuration.

    All endpoints are supplied explicitly (no discovery round-trip) so the
    client can be constructed and exercised entirely offline.
    """

    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: Optional[str] = None
    scopes: tuple[str, ...] = ("openid", "email", "profile")


def _default_token_exchanger(
    token_endpoint: str, data: Mapping[str, str]
) -> Mapping[str, Any]:
    """Default :data:`TokenExchanger`: POST the form to the token endpoint.

    Imported lazily so merely importing this module never requires network
    libraries to be available at call sites that inject their own exchanger.
    """
    import httpx

    response = httpx.post(token_endpoint, data=dict(data), timeout=30.0)
    response.raise_for_status()
    return response.json()


def _decode_claims(id_token: str) -> Mapping[str, Any]:
    """Default :data:`IdTokenVerifier`: decode the ID token's claims.

    This decodes the payload with ``python-jose`` *without* signature
    verification, which is **not** sufficient for production — real wiring must
    supply a ``verifier`` that fetches the JWKS (``jwks_uri``) and validates the
    signature, ``iss``, ``aud``, ``exp`` and ``nonce``. It exists so the module
    has a working default; production injects a verifying callable.
    """
    from jose import jwt
    from jose.exceptions import JWTError

    try:
        return jwt.get_unverified_claims(id_token)
    except JWTError as exc:  # pragma: no cover - exercised via fake in tests
        raise AuthError(f"invalid id_token: {exc}") from exc


def _roles_from_claims(claims: Mapping[str, Any]) -> frozenset[Role]:
    """Map an optional ``groups``/``roles`` claim onto :class:`Role` values."""
    raw: Any = claims.get("roles")
    if raw is None:
        raw = claims.get("groups")
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        candidates = [raw]
    else:
        candidates = [str(item) for item in raw]
    mapped = {
        _ROLE_ALIASES[name.strip().lower()]
        for name in candidates
        if name.strip().lower() in _ROLE_ALIASES
    }
    return frozenset(mapped)


@dataclass(frozen=True)
class OidcClient:
    """Authorization-code OIDC client built from an :class:`OidcConfig`."""

    config: OidcConfig
    token_exchanger: TokenExchanger = field(default=_default_token_exchanger)
    verifier: IdTokenVerifier = field(default=_decode_claims)

    def authorization_url(self, state: str, nonce: str) -> str:
        """Build the IdP ``/authorize`` redirect URL (no network).

        :param state: opaque CSRF token the caller must round-trip and verify.
        :param nonce: replay-protection value bound into the ID token.
        """
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": state,
            "nonce": nonce,
        }
        return f"{self.config.authorization_endpoint}?{urlencode(params)}"

    def exchange_code(
        self, code: str, *, token_exchanger: Optional[TokenExchanger] = None
    ) -> dict[str, Any]:
        """Exchange an authorization ``code`` for a token response.

        :param code: the authorization code returned on the redirect.
        :param token_exchanger: optional override of the HTTP POST seam; tests
            inject a fake so no real request is made.
        :raises AuthError: if the exchange fails or returns no tokens.
        """
        exchanger = token_exchanger or self.token_exchanger
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        try:
            tokens = exchanger(self.config.token_endpoint, data)
        except Exception as exc:  # noqa: BLE001 - normalise transport failures
            raise AuthError(f"token exchange failed: {exc}") from exc
        if not tokens:
            raise AuthError("token exchange returned no tokens")
        return dict(tokens)

    def principal_from_id_token(
        self, id_token: str, *, verifier: Optional[IdTokenVerifier] = None
    ) -> Principal:
        """Decode an ID token into a :class:`Principal`.

        :param id_token: the compact-serialised JWT ID token.
        :param verifier: optional override of the decode/verify seam; tests
            inject a fake returning a claims mapping.
        :raises AuthError: if the token is missing, undecodable, or lacks a
            usable subject identifier.
        """
        if not id_token:
            raise AuthError("missing id_token")
        decode = verifier or self.verifier
        try:
            claims = decode(id_token)
        except AuthError:
            raise
        except Exception as exc:  # noqa: BLE001 - any decode failure is auth failure
            raise AuthError(f"invalid id_token: {exc}") from exc
        if not claims:
            raise AuthError("id_token has no claims")

        sub = claims.get("sub")
        if not sub:
            raise AuthError("id_token missing 'sub' claim")
        username = (
            claims.get("preferred_username")
            or claims.get("email")
            or claims.get("name")
            or str(sub)
        )
        return Principal(
            user_id=str(sub),
            username=str(username),
            roles=_roles_from_claims(claims),
        )
