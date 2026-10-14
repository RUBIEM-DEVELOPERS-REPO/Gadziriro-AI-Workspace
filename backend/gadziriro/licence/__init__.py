"""Gadziriro licence (Phase 1): offline, signed licence-key validation (FR-31)."""

from __future__ import annotations

from .key import LicenceError, LicenceInfo, issue_licence, validate_licence

__all__ = [
    "LicenceError",
    "LicenceInfo",
    "issue_licence",
    "validate_licence",
]
