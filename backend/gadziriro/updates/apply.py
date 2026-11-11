"""Apply / roll back signed updates (FR-30).

Updates are verified before anything changes; the previous version is retained so a
single ``rollback()`` reverts. Works online or from an admin-carried offline bundle
(air-gapped, NFR-11). No network is ever used.
"""

from __future__ import annotations

from pathlib import Path

from nacl.signing import VerifyKey

from ..core.errors import GadziriroError
from .signing import UpdateError, UpdatePackage, verify_update


def _cmp(a: str, b: str) -> int:
    """Compare dotted versions; returns -1/0/1."""

    def parts(v: str) -> list[int]:
        out = []
        for p in v.split("."):
            try:
                out.append(int(p))
            except ValueError:
                out.append(0)
        return out

    pa, pb = parts(a), parts(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return (pa > pb) - (pa < pb)


class UpdateManager:
    """Tracks the current version and applies/rolls back verified updates."""

    def __init__(
        self,
        *,
        verify_key: VerifyKey | bytes,
        current_version: str = "0.0.0",
        audit=None,
    ) -> None:
        self._verify_key = verify_key
        self._current = current_version
        self._previous: str | None = None
        self._history: list[dict] = []
        self._audit = audit

    @property
    def current_version(self) -> str:
        return self._current

    def _log(self, action: str, version: str) -> None:
        if self._audit is None:
            return
        from ..audit.base import AuditEvent

        self._audit.append(
            AuditEvent(
                actor="system",
                action=action,
                target=version,
                level="security",
                meta={"from": self._previous, "to": self._current},
            )
        )

    def apply_update(self, bundle: bytes, *, force: bool = False) -> str:
        """Verify and apply an update bundle; return the new current version."""
        pkg: UpdatePackage = verify_update(bundle, self._verify_key)
        if not force and _cmp(pkg.version, self._current) <= 0:
            raise UpdateError(
                f"refusing downgrade/duplicate: {pkg.version} <= {self._current}"
            )
        self._previous = self._current
        self._current = pkg.version
        self._history.append({"action": "apply", "version": pkg.version})
        self._log("update.apply", pkg.version)
        return self._current

    def import_offline_bundle(self, source) -> str:
        """Apply a signed bundle carried in on disk/bytes (air-gapped path)."""
        if isinstance(source, (str, Path)):
            data = Path(source).read_bytes()
        elif isinstance(source, (bytes, bytearray)):
            data = bytes(source)
        else:
            raise GadziriroError("offline bundle must be a path or bytes")
        return self.apply_update(data)

    def rollback(self) -> str:
        """Revert to the previously applied version (one-step)."""
        if self._previous is None:
            raise UpdateError("no previous version to roll back to")
        rolled_to = self._previous
        self._previous = None
        self._current = rolled_to
        self._history.append({"action": "rollback", "version": rolled_to})
        self._log("update.rollback", rolled_to)
        return self._current

    def history(self) -> list[dict]:
        return list(self._history)
