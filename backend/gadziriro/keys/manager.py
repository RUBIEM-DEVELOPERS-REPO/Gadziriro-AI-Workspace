"""Customer-held data keys with on-demand rotation (FR-41).

Encryption keys are *customer-held*: they are generated and stored on the
customer's own machine and **never leave it** (no cloud KMS, no network). The
:class:`KeyManager` keeps a set of *versioned* AES-256-GCM data keys on local
disk. Ciphertext is wrapped in a small envelope that records which key version
produced it, so:

* :meth:`KeyManager.rotate` can mint a new current key while retaining the old
  ones, and
* :meth:`KeyManager.decrypt` can still decrypt data written under any previous
  version after a rotation.

Envelope layout (all big-endian)::

    magic   4 bytes  b"GZK1"
    version 4 bytes  uint32 key version used
    nonce  12 bytes  AES-GCM nonce
    ct      N bytes  AES-GCM ciphertext || tag

Keys are persisted as a JSON keyring under ``<data_dir>/keys`` (or an explicit
directory). On POSIX the keyring file is created with ``0o600`` permissions
(owner-only); Windows ignores the mode, but the intent — no other local user
may read the keys — is documented and applied where the OS supports it.
"""

from __future__ import annotations

import base64
import json
import os
import struct
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..core.config import Settings
from ..core.errors import GadziriroError

_MAGIC = b"GZK1"
_HEADER = struct.Struct(">4sI")  # magic + version
_NONCE_LEN = 12
_KEY_LEN = 32  # AES-256
_KEYRING_NAME = "keyring.json"


class KeyError_(GadziriroError):
    """A key-management failure (missing version, corrupt envelope, bad tag).

    Named with a trailing underscore to avoid shadowing the builtin
    :class:`KeyError`; exported as :data:`KeyManagerError`.
    """


# Public alias (avoids the builtin-name collision at call sites).
KeyManagerError = KeyError_


class KeyManager:
    """Versioned, customer-held AES-GCM key store with rotation (FR-41)."""

    def __init__(self, store: Optional[Path | str | Settings] = None) -> None:
        """Create or load a keyring.

        :param store: where keys live. A :class:`~pathlib.Path`/str is used as
            the keyring *directory*; a :class:`Settings` uses
            ``settings.data_dir / "keys"``; ``None`` falls back to the default
            :class:`Settings`.
        """
        if isinstance(store, Settings):
            key_dir = store.data_dir / "keys"
        elif store is None:
            key_dir = Settings().data_dir / "keys"
        else:
            key_dir = Path(store)
        self._dir = key_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / _KEYRING_NAME
        self._keys: dict[int, bytes] = {}
        self._current: int = 0
        self._load()
        if not self._keys:
            self.generate()

    # -- persistence -----------------------------------------------------

    def _load(self) -> None:
        """Load the keyring from disk, if present."""
        if not self._path.is_file():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._current = int(raw["current"])
        self._keys = {
            int(version): base64.b64decode(material)
            for version, material in raw["keys"].items()
        }

    def _save(self) -> None:
        """Persist the keyring to disk with owner-only intent (0600)."""
        payload = {
            "current": self._current,
            "keys": {
                str(version): base64.b64encode(material).decode("ascii")
                for version, material in self._keys.items()
            },
        }
        data = json.dumps(payload, indent=2).encode("utf-8")
        # Create with 0600 where the OS honours it (POSIX); Windows ignores mode.
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        try:
            os.chmod(self._path, 0o600)
        except OSError:  # pragma: no cover - best-effort on unsupported FS
            pass

    # -- key lifecycle ---------------------------------------------------

    @property
    def current_version(self) -> int:
        """The version of the key currently used to encrypt new data."""
        return self._current

    def versions(self) -> list[int]:
        """All retained key versions (ascending), newest usable for decrypt."""
        return sorted(self._keys)

    def generate(self) -> int:
        """Mint the next key version, make it current, and persist.

        :returns: the new current key version.
        """
        next_version = (max(self._keys) + 1) if self._keys else 1
        self._keys[next_version] = AESGCM.generate_key(bit_length=_KEY_LEN * 8)
        self._current = next_version
        self._save()
        return self._current

    def rotate(self) -> int:
        """Rotate to a fresh current key, retaining all prior keys for decrypt.

        Customers invoke this on demand (FR-41). Data already encrypted under an
        older version keeps decrypting because that version stays in the ring.

        :returns: the new current key version.
        """
        return self.generate()

    # -- crypto ----------------------------------------------------------

    def _key(self, version: int) -> bytes:
        try:
            return self._keys[version]
        except KeyError as exc:
            raise KeyError_(f"unknown key version: {version}") from exc

    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt ``plaintext`` under the current key, returning an envelope.

        The returned bytes embed the key version used, so :meth:`decrypt` can
        route to the right key even after rotations.
        """
        version = self._current
        aesgcm = AESGCM(self._key(version))
        nonce = os.urandom(_NONCE_LEN)
        header = _HEADER.pack(_MAGIC, version)
        ct = aesgcm.encrypt(nonce, plaintext, header)
        return header + nonce + ct

    def decrypt(self, token: bytes) -> bytes:
        """Decrypt an envelope produced by :meth:`encrypt`.

        Selects the key version recorded in the envelope header, so data written
        before a rotation still decrypts.

        :raises KeyManagerError: if the envelope is malformed, names an unknown
            key version, or fails authentication.
        """
        if len(token) < _HEADER.size + _NONCE_LEN:
            raise KeyError_("ciphertext envelope too short")
        magic, version = _HEADER.unpack(token[: _HEADER.size])
        if magic != _MAGIC:
            raise KeyError_("unrecognised ciphertext envelope")
        header = token[: _HEADER.size]
        nonce = token[_HEADER.size : _HEADER.size + _NONCE_LEN]
        ct = token[_HEADER.size + _NONCE_LEN :]
        aesgcm = AESGCM(self._key(version))
        try:
            return aesgcm.decrypt(nonce, ct, header)
        except InvalidTag as exc:
            raise KeyError_("ciphertext authentication failed") from exc
