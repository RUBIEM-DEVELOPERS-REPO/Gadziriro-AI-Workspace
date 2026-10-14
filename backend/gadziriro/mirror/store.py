"""Object-store-backed mirror with a scanning proxy (FR-29, NFR-12).

``ObjectStoreMirror`` is the single source of packages AND models for the
workspace. Nothing is ever fetched from the internet: an artifact exists in the
mirror only because an admin explicitly added it, and every add is vetted by a
:class:`~gadziriro.mirror.base.Scanner` first, so a blocked artifact is never
stored.

Storage layout (keys under the backing :class:`ObjectStore`)::

    <kind>/<name>/<version>/data        raw artifact bytes
    <kind>/<name>/<version>/meta.json   canonical-JSON meta (name/version/sha256)

where ``kind`` is ``"package"`` or ``"model"``. ``get_*`` reads only from the
store and raises :class:`NotFound` for anything not previously added -- there is
deliberately NO fallback path to the network.
"""

from __future__ import annotations

import json
from typing import Any

from ..core.canonical_json import canonical_bytes
from ..core.crypto import sha256_hex
from ..core.errors import GadziriroError, NotFound
from ..core.objectstore import ObjectStore
from .base import Scanner, SignatureScanner

_PACKAGE = "package"
_MODEL = "model"


class ObjectStoreMirror:
    """Approved-only, offline mirror for packages and models.

    Parameters
    ----------
    store:
        Backing byte-blob store (e.g. ``LocalObjectStore``).
    scanner:
        Scanning proxy run on every add; defaults to :class:`SignatureScanner`.
    """

    def __init__(self, store: ObjectStore, *, scanner: Scanner | None = None) -> None:
        self._store = store
        self._scanner: Scanner = scanner if scanner is not None else SignatureScanner()

    # -- key helpers -------------------------------------------------------

    @staticmethod
    def _data_key(kind: str, name: str, version: str) -> str:
        return f"{kind}/{name}/{version}/data"

    @staticmethod
    def _meta_key(kind: str, name: str, version: str) -> str:
        return f"{kind}/{name}/{version}/meta.json"

    # -- generic implementation -------------------------------------------

    def _add(self, kind: str, name: str, version: str, data: bytes) -> dict[str, Any]:
        """Scan then store ``data`` for ``kind``; return the meta record.

        The scanner runs BEFORE anything is written, so a blocked artifact
        (``PolicyDenied``) leaves the store untouched.
        """
        self._scanner.scan(name, data)  # raises PolicyDenied -> nothing stored
        meta: dict[str, Any] = {
            "kind": kind,
            "name": name,
            "version": version,
            "size": len(data),
            "sha256": sha256_hex(data),
        }
        self._store.put(self._data_key(kind, name, version), data)
        self._store.put(self._meta_key(kind, name, version), canonical_bytes(meta))
        return meta

    def _has(self, kind: str, name: str, version: str) -> bool:
        return self._store.exists(self._data_key(kind, name, version))

    def _get(self, kind: str, name: str, version: str) -> bytes:
        key = self._data_key(kind, name, version)
        if not self._store.exists(key):
            # No network fallback -- this IS the privacy guarantee (NFR-12).
            raise NotFound(f"{kind} not in mirror: {name}=={version}")
        data = self._store.get(key)
        meta = self._meta(kind, name, version)
        actual = sha256_hex(data)
        if actual != meta.get("sha256"):
            raise GadziriroError(
                f"{kind} checksum mismatch for {name}=={version}: "
                f"stored {meta.get('sha256')} but read {actual}"
            )
        return data

    def _meta(self, kind: str, name: str, version: str) -> dict[str, Any]:
        key = self._meta_key(kind, name, version)
        if not self._store.exists(key):
            raise NotFound(f"{kind} meta not in mirror: {name}=={version}")
        return json.loads(self._store.get(key).decode("utf-8"))

    def _list(self, kind: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for key in self._store.list(f"{kind}/"):
            if not key.endswith("/meta.json"):
                continue
            meta = json.loads(self._store.get(key).decode("utf-8"))
            out.append((meta["name"], meta["version"]))
        return sorted(out)

    # -- packages ----------------------------------------------------------

    def add_package(self, name: str, version: str, data: bytes) -> dict[str, Any]:
        """Scan then store a package; raise ``PolicyDenied`` if blocked."""
        return self._add(_PACKAGE, name, version, data)

    def has_package(self, name: str, version: str) -> bool:
        """Return ``True`` iff the package was previously added."""
        return self._has(_PACKAGE, name, version)

    def get_package(self, name: str, version: str) -> bytes:
        """Return package bytes; raise :class:`NotFound` if never added."""
        return self._get(_PACKAGE, name, version)

    def package_meta(self, name: str, version: str) -> dict[str, Any]:
        """Return the stored meta record (name/version/size/sha256)."""
        return self._meta(_PACKAGE, name, version)

    def list_packages(self) -> list[tuple[str, str]]:
        """Return the ``(name, version)`` pairs currently mirrored."""
        return self._list(_PACKAGE)

    # -- models ------------------------------------------------------------

    def add_model(self, name: str, version: str, data: bytes) -> dict[str, Any]:
        """Scan then store a model; raise ``PolicyDenied`` if blocked."""
        return self._add(_MODEL, name, version, data)

    def has_model(self, name: str, version: str) -> bool:
        """Return ``True`` iff the model was previously added."""
        return self._has(_MODEL, name, version)

    def get_model(self, name: str, version: str) -> bytes:
        """Return model bytes; raise :class:`NotFound` if never added."""
        return self._get(_MODEL, name, version)

    def model_meta(self, name: str, version: str) -> dict[str, Any]:
        """Return the stored meta record (name/version/size/sha256)."""
        return self._meta(_MODEL, name, version)

    def list_models(self) -> list[tuple[str, str]]:
        """Return the ``(name, version)`` pairs currently mirrored."""
        return self._list(_MODEL)
