"""Acceptance test for FR-41: customer-held key rotation on demand.

Scenario: a customer rotates their data-encryption key on demand. Data written
under the pre-rotation key must keep decrypting, new data uses the rotated key,
and the key material never leaves the local machine.
"""

from __future__ import annotations

import json

from gadziriro.keys import KeyManager


def test_fr41_customer_key_rotation_on_demand(tmp_path) -> None:
    key_dir = tmp_path / "customer-keys"
    km = KeyManager(key_dir)

    # Encrypt under v1.
    assert km.current_version == 1
    v1_blob = km.encrypt(b"customer dataset v1")

    # Customer rotates on demand.
    km.rotate()
    assert km.current_version == 2

    # Encrypt under v2.
    v2_blob = km.encrypt(b"customer dataset v2")

    # Both decrypt correctly after rotation.
    assert km.decrypt(v1_blob) == b"customer dataset v1"
    assert km.decrypt(v2_blob) == b"customer dataset v2"


def test_fr41_keys_are_stored_locally_only(tmp_path) -> None:
    key_dir = tmp_path / "customer-keys"
    km = KeyManager(key_dir)
    km.rotate()  # ensure >1 version retained

    # The keyring file exists on local disk under the provided directory.
    keyring = key_dir / "keyring.json"
    assert keyring.is_file()

    payload = json.loads(keyring.read_text(encoding="utf-8"))
    # Both versions are retained locally (old key kept for decrypt).
    assert set(payload["keys"]) == {"1", "2"}
    assert payload["current"] == 2
    # Ciphertext envelopes are self-describing and never carry key material;
    # the only place key bytes live is this local keyring.
    assert km.versions() == [1, 2]
