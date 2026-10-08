"""Unit tests for offline licence-key validation (FR-31)."""

from __future__ import annotations

from datetime import date

import pytest
from nacl.signing import SigningKey

from gadziriro.licence.key import (
    LicenceError,
    LicenceInfo,
    issue_licence,
    validate_licence,
)


def _keypair() -> tuple[SigningKey, object]:
    sk = SigningKey.generate()
    return sk, sk.verify_key


def _info() -> LicenceInfo:
    return LicenceInfo(
        customer="RUBIEM",
        expiry="2030-01-01",
        features=("notebooks", "gpu"),
        seats=25,
    )


def test_valid_key_round_trips() -> None:
    sk, vk = _keypair()
    token = issue_licence(_info(), sk)

    info = validate_licence(token, vk, now=date(2026, 10, 8))

    assert info == _info()
    assert info.customer == "RUBIEM"
    assert info.features == ("notebooks", "gpu")
    assert info.seats == 25


def test_verify_key_accepts_raw_bytes() -> None:
    sk, vk = _keypair()
    token = issue_licence(_info(), sk)

    info = validate_licence(token, bytes(vk), now=date(2026, 10, 8))

    assert info.customer == "RUBIEM"


def test_tampered_token_raises() -> None:
    sk, vk = _keypair()
    token = issue_licence(_info(), sk)

    payload, sig = token.split(".")
    # Flip the last char of the payload -> signature no longer matches.
    mutated = payload[:-1] + ("A" if payload[-1] != "A" else "B")
    tampered = f"{mutated}.{sig}"

    with pytest.raises(LicenceError):
        validate_licence(tampered, vk, now=date(2026, 10, 8))


def test_wrong_key_raises() -> None:
    sk, _ = _keypair()
    _, other_vk = _keypair()
    token = issue_licence(_info(), sk)

    with pytest.raises(LicenceError):
        validate_licence(token, other_vk, now=date(2026, 10, 8))


def test_expired_key_raises() -> None:
    sk, vk = _keypair()
    token = issue_licence(LicenceInfo(customer="RUBIEM", expiry="2024-01-01"), sk)

    with pytest.raises(LicenceError):
        validate_licence(token, vk, now=date(2026, 10, 8))


def test_malformed_token_raises() -> None:
    _, vk = _keypair()
    with pytest.raises(LicenceError):
        validate_licence("not-a-valid-token", vk, now=date(2026, 10, 8))
