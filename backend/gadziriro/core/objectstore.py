"""Object store abstraction (shared by registry, mirror, backup).

Phase 0 kept everything on local disk; Phase 1 introduces a small S3-compatible
surface so the registry, the package/model mirror, and the backup service all
speak the same storage API. ``LocalObjectStore`` is the single-node default
(MinIO slots in later, Phase 3, by implementing ``ObjectStore``).

Keys are POSIX-style forward-slash paths relative to the store root; values are
bytes. The store never reaches the network (privacy default).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from .errors import NotFound


@runtime_checkable
class ObjectStore(Protocol):
    """Minimal byte-blob store keyed by forward-slash paths."""

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def list(self, prefix: str = "") -> list[str]: ...

    def delete(self, key: str) -> None: ...


class LocalObjectStore:
    """Filesystem-backed :class:`ObjectStore` rooted at a directory.

    Keys map to files under ``root``; parent directories are created on write.
    Path traversal outside the root is rejected.
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self._root / key).resolve()
        root = self._root.resolve()
        if root != p and root not in p.parents:
            raise ValueError(f"key escapes object-store root: {key!r}")
        return p

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        p = self._path(key)
        if not p.is_file():
            raise NotFound(f"object not found: {key}")
        return p.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str = "") -> list[str]:
        base = self._path(prefix) if prefix else self._root
        if base.is_file():
            return [prefix]
        if not base.exists():
            return []
        out: list[str] = []
        for f in base.rglob("*"):
            if f.is_file():
                out.append(f.relative_to(self._root).as_posix())
        return sorted(out)

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.is_dir():
            shutil.rmtree(p)
        elif p.is_file():
            p.unlink()

    def iter_prefixes(self, prefix: str = "") -> Iterable[str]:
        """Yield immediate child directory names under ``prefix`` (helper)."""
        base = self._path(prefix) if prefix else self._root
        if not base.exists():
            return
        for child in sorted(base.iterdir()):
            if child.is_dir():
                yield child.name
