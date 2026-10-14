"""Gadziriro licensing (Phase 2 Model Studio).

Licence and export-control checks (FR-48): gate a base model's use and export
against its licence and export-restriction status before either happens.
"""

from .checks import (
    ALLOWED_EXPORT_DESTINATIONS,
    LICENCE_TABLE,
    UNKNOWN_LICENCE,
    LicenceRecord,
    check_export_control,
    check_licence,
    licence_for,
    register_licence,
)

__all__ = [
    "LicenceRecord",
    "LICENCE_TABLE",
    "UNKNOWN_LICENCE",
    "ALLOWED_EXPORT_DESTINATIONS",
    "licence_for",
    "check_licence",
    "check_export_control",
    "register_licence",
]
