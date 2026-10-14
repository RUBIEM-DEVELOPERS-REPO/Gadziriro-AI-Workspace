"""Repeatable, pinned environments served from the mirror (FR-34).

Reproducibility means: the exact same set of pinned package versions, pulled from
the approved offline mirror — not from the open internet. An
:class:`EnvironmentSpec` names a base image and a fully pinned package set, can
produce a stable ``lock_hash`` identifying that set, and can ``resolve`` itself
against a mirror to prove every pin is actually available (and therefore
reproducible) before anyone builds on it.

The mirror is referenced by *structural typing*: any object exposing
``has_package(name: str, version: str) -> bool`` works, so this module never
imports the mirror package.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..core.errors import GadziriroError

DEFAULT_BASE_IMAGE = "gadziriro/kernel:py311"


class UnresolvedEnvironment(GadziriroError):
    """One or more pinned packages are not available in the mirror (FR-34)."""


@runtime_checkable
class PackageSource(Protocol):
    """Structural view of a mirror: can it serve a pinned package?"""

    def has_package(self, name: str, version: str) -> bool:
        """True if ``name==version`` is available to be served offline."""
        ...


@dataclass(frozen=True)
class EnvironmentSpec:
    """A reproducible environment: a base image plus fully pinned packages."""

    name: str
    packages: dict[str, str]  # package name -> EXACT version
    base_image: str = DEFAULT_BASE_IMAGE

    def lock_hash(self) -> str:
        """Return a stable SHA-256 over the base image and the pinned set.

        Order-independent (keys are sorted), so the same pins always hash the
        same; changing any version (or the base image) changes the hash.
        """
        canonical = json.dumps(
            {
                "base_image": self.base_image,
                "packages": dict(sorted(self.packages.items())),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def resolve(self, mirror: PackageSource) -> bool:
        """Verify every pinned package is available in ``mirror``.

        :returns: ``True`` when all pins resolve.
        :raises UnresolvedEnvironment: listing the missing ``name==version`` pins,
            because an environment that cannot be served from the mirror is not
            reproducible.
        """
        missing = [
            f"{name}=={version}"
            for name, version in sorted(self.packages.items())
            if not mirror.has_package(name, version)
        ]
        if missing:
            raise UnresolvedEnvironment(
                f"environment {self.name!r} is not reproducible; "
                f"missing from mirror: {', '.join(missing)}"
            )
        return True
