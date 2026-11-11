"""Unit tests for signed update build/verify."""

from __future__ import annotations

import pytest
from nacl.signing import SigningKey

from gadziriro.updates.signing import UpdateError, build_update, verify_update


def _keys():
    sk = SigningKey.generate()
    return sk, sk.verify_key


def test_build_verify_roundtrip() -> None:
    sk, vk = _keys()
    bundle, manifest = build_update("1.2.0", b"payload-bytes", sk, notes="hi")
    pkg = verify_update(bundle, vk)
    assert pkg.version == "1.2.0"
    assert pkg.size == len(b"payload-bytes")
    assert pkg.notes == "hi"
    assert manifest["version"] == "1.2.0"


def test_tampered_payload_rejected() -> None:
    sk, vk = _keys()
    bundle, _ = build_update("1.0.0", b"good", sk)
    tampered = bundle.replace(b"good", b"evil")
    with pytest.raises(UpdateError):
        verify_update(tampered, vk)


def test_wrong_key_rejected() -> None:
    sk, _ = _keys()
    _, other_vk = _keys()
    bundle, _ = build_update("1.0.0", b"x", sk)
    with pytest.raises(UpdateError):
        verify_update(bundle, other_vk)


def test_malformed_bundle_rejected() -> None:
    _, vk = _keys()
    with pytest.raises(UpdateError):
        verify_update(b"not-a-bundle", vk)
