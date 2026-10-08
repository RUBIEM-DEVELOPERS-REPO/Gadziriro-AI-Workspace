"""Mirror contracts: scanning proxy + approved-only package/model mirror (FR-29).

The workspace is air-gapped by default (NFR-01/NFR-02): user code must never
reach the public internet to fetch a package or a model. Instead an admin
*adds* an artifact to a local mirror, and that mirror is the ONLY place the
workspace is ever served from. Every artifact passes a scanning proxy on the
way in -- a stand-in for the real malware/CVE scanning gateway -- so that a
blocked artifact is never stored and therefore never servable.

This module defines the structural contracts; :mod:`gadziriro.mirror.store`
provides the object-store-backed implementation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core.errors import PolicyDenied


@runtime_checkable
class Scanner(Protocol):
    """A scanning proxy that vets an artifact before it may be stored.

    Implementations inspect ``data`` and raise :class:`PolicyDenied` when the
    artifact is blocked; returning normally means the artifact is approved.
    """

    def scan(self, name: str, data: bytes) -> None:
        """Vet ``data`` for ``name``; raise :class:`PolicyDenied` if blocked."""
        ...


# A small default deny-list. The EICAR test string is the industry-standard
# "this is safe to use as a positive" marker; the second is a local sentinel so
# tests have a stable, obviously-synthetic trigger.
DEFAULT_BAD_SIGNATURES: tuple[bytes, ...] = (
    b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE",
    b"GADZIRIRO-BLOCKED-ARTIFACT",
)


class SignatureScanner:
    """Default :class:`Scanner`: block artifacts matching a byte-marker deny-list.

    This is a deliberately simple stand-in for the production scanning proxy
    (malware signatures / CVE lookups): any artifact whose bytes contain one of
    the configured ``bad_signatures`` is rejected with :class:`PolicyDenied`.
    """

    def __init__(
        self, bad_signatures: tuple[bytes, ...] = DEFAULT_BAD_SIGNATURES
    ) -> None:
        self._bad_signatures = tuple(bad_signatures)

    def scan(self, name: str, data: bytes) -> None:
        """Raise :class:`PolicyDenied` if ``data`` matches a bad signature."""
        for sig in self._bad_signatures:
            if sig in data:
                raise PolicyDenied(
                    f"artifact {name!r} blocked by scanner: matched bad signature"
                )


@runtime_checkable
class PackageMirror(Protocol):
    """Approved-only mirror of packages. No network fallback, ever."""

    def has_package(self, name: str, version: str) -> bool:
        """Return ``True`` iff ``name``/``version`` was previously added."""
        ...

    def add_package(self, name: str, version: str, data: bytes) -> dict:
        """Scan then store ``data``; return its meta record. Raises on block."""
        ...

    def get_package(self, name: str, version: str) -> bytes:
        """Return stored bytes; raise :class:`NotFound` if never added."""
        ...

    def list_packages(self) -> list[tuple[str, str]]:
        """Return ``(name, version)`` pairs currently mirrored."""
        ...
