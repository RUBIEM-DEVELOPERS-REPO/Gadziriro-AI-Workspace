"""Unit tests for customer-held key management + rotation (FR-41)."""

from __future__ import annotations

import pytest

from gadziriro.keys import KeyManager, KeyManagerError


def test_encrypt_decrypt_round_trip(tmp_path) -> None:
    km = KeyManager(tmp_path / "keys")
    token = km.encrypt(b"secret payload")
    assert token != b"secret payload"
    assert km.decrypt(token) == b"secret payload"


def test_current_version_starts_at_one(tmp_path) -> None:
    km = KeyManager(tmp_path / "keys")
    assert km.current_version == 1


def test_rotate_increments_version_and_old_data_still_decrypts(tmp_path) -> None:
    km = KeyManager(tmp_path / "keys")
    v1 = km.current_version
    old_token = km.encrypt(b"before rotation")

    new_version = km.rotate()
    assert new_version == v1 + 1
    assert km.current_version == new_version

    # New data uses the new key.
    new_token = km.encrypt(b"after rotation")
    assert km.decrypt(new_token) == b"after rotation"

    # Data encrypted under the old key still decrypts.
    assert km.decrypt(old_token) == b"before rotation"


def test_keyring_persists_across_instances(tmp_path) -> None:
    key_dir = tmp_path / "keys"
    km1 = KeyManager(key_dir)
    token = km1.encrypt(b"persisted")
    km1.rotate()

    km2 = KeyManager(key_dir)
    assert km2.current_version == 2
    assert km2.decrypt(token) == b"persisted"


def test_tampered_ciphertext_fails_authentication(tmp_path) -> None:
    km = KeyManager(tmp_path / "keys")
    token = bytearray(km.encrypt(b"authentic"))
    token[-1] ^= 0x01  # flip a bit in the tag
    with pytest.raises(KeyManagerError):
        km.decrypt(bytes(token))


def test_bad_envelope_raises(tmp_path) -> None:
    km = KeyManager(tmp_path / "keys")
    with pytest.raises(KeyManagerError):
        km.decrypt(b"too-short")
    with pytest.raises(KeyManagerError):
        km.decrypt(b"BADMAGIC" + b"\x00" * 32)
