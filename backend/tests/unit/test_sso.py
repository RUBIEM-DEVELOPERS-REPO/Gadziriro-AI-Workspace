"""Unit tests for the OIDC authorization-code SSO client (FR-16b)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from gadziriro.auth.base import Role
from gadziriro.auth.sso import OidcClient, OidcConfig
from gadziriro.core.errors import AuthError


@pytest.fixture()
def config() -> OidcConfig:
    return OidcConfig(
        issuer="https://idp.example.com",
        client_id="gadziriro-client",
        client_secret="s3cret",
        redirect_uri="https://workspace.local/callback",
        authorization_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/token",
        jwks_uri="https://idp.example.com/jwks",
    )


def test_authorization_url_contains_required_params(config: OidcConfig) -> None:
    client = OidcClient(config)
    url = client.authorization_url(state="xyz-state", nonce="nnn")

    parsed = urlparse(url)
    assert parsed.scheme + "://" + parsed.netloc + parsed.path == (
        config.authorization_endpoint
    )
    qs = parse_qs(parsed.query)
    assert qs["client_id"] == [config.client_id]
    assert qs["redirect_uri"] == [config.redirect_uri]
    assert qs["state"] == ["xyz-state"]
    assert qs["nonce"] == ["nnn"]
    assert qs["response_type"] == ["code"]
    assert qs["scope"] == ["openid email profile"]


def test_exchange_code_uses_injected_exchanger(config: OidcConfig) -> None:
    captured: dict[str, object] = {}

    def fake_exchanger(endpoint: str, data):
        captured["endpoint"] = endpoint
        captured["data"] = dict(data)
        return {"access_token": "at", "id_token": "it", "token_type": "Bearer"}

    client = OidcClient(config)
    tokens = client.exchange_code("the-code", token_exchanger=fake_exchanger)

    assert tokens["access_token"] == "at"
    assert tokens["id_token"] == "it"
    assert captured["endpoint"] == config.token_endpoint
    assert captured["data"]["code"] == "the-code"
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["client_id"] == config.client_id


def test_exchange_code_empty_response_raises(config: OidcConfig) -> None:
    client = OidcClient(config)
    with pytest.raises(AuthError):
        client.exchange_code("code", token_exchanger=lambda ep, d: {})


def test_principal_from_id_token_with_fake_verifier(config: OidcConfig) -> None:
    def fake_verifier(token: str):
        assert token == "the-id-token"
        return {
            "sub": "user-123",
            "preferred_username": "alice",
            "email": "alice@example.com",
            "groups": ["analyst", "unknown-group"],
        }

    client = OidcClient(config)
    principal = client.principal_from_id_token("the-id-token", verifier=fake_verifier)

    assert principal.user_id == "user-123"
    assert principal.username == "alice"
    assert principal.roles == frozenset({Role.ANALYST})


def test_principal_falls_back_to_email_then_sub(config: OidcConfig) -> None:
    client = OidcClient(config)
    principal = client.principal_from_id_token(
        "tok", verifier=lambda t: {"sub": "u9", "email": "bob@example.com"}
    )
    assert principal.username == "bob@example.com"
    assert principal.roles == frozenset()


def test_invalid_id_token_raises_autherror(config: OidcConfig) -> None:
    client = OidcClient(config)

    def boom(token: str):
        raise ValueError("bad signature")

    with pytest.raises(AuthError):
        client.principal_from_id_token("whatever", verifier=boom)


def test_missing_id_token_raises_autherror(config: OidcConfig) -> None:
    client = OidcClient(config)
    with pytest.raises(AuthError):
        client.principal_from_id_token("", verifier=lambda t: {"sub": "x"})


def test_id_token_without_sub_raises(config: OidcConfig) -> None:
    client = OidcClient(config)
    with pytest.raises(AuthError):
        client.principal_from_id_token("tok", verifier=lambda t: {"email": "a@b"})
