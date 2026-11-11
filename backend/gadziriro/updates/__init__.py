"""Signed updates + offline bundles (FR-30)."""

from .apply import UpdateManager
from .signing import UpdateError, UpdatePackage, build_update, verify_update

__all__ = [
    "build_update",
    "verify_update",
    "UpdatePackage",
    "UpdateError",
    "UpdateManager",
]
