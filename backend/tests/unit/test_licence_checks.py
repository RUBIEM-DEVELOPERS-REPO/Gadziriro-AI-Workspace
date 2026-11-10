"""Unit tests for licence + export-control checks (FR-48)."""

from __future__ import annotations

import pytest

from gadziriro.core.errors import PolicyDenied
from gadziriro.licensing import (
    LicenceRecord,
    check_export_control,
    check_licence,
    licence_for,
    register_licence,
)


def test_non_commercial_licence_blocks_commercial_use() -> None:
    # The "research" family is non-commercial in the table.
    with pytest.raises(PolicyDenied):
        check_licence("research-7b", intended_use="commercial")


def test_non_commercial_licence_allows_non_commercial_use() -> None:
    # Same model, non-commercial intent, passes.
    check_licence("research-7b", intended_use="non-commercial")


def test_permissive_licence_allows_commercial_use() -> None:
    # Mistral is Apache-2.0: commercial use passes without raising.
    check_licence("mistral-7b-instruct", intended_use="commercial")


def test_export_restricted_model_to_disallowed_destination_denied() -> None:
    # Qwen is flagged export-restricted; an overseas destination is denied.
    with pytest.raises(PolicyDenied):
        check_export_control("qwen2-7b", destination="overseas")


def test_export_restricted_model_to_allowed_destination_passes() -> None:
    check_export_control("qwen2-7b", destination="domestic")


def test_unrestricted_model_exports_anywhere() -> None:
    # Llama is not export-restricted: any destination passes.
    check_export_control("llama-3-8b", destination="overseas")


def test_unknown_family_is_conservative_record() -> None:
    rec = licence_for("totally-novel-model")
    assert rec["licence_id"] == "unknown"
    assert rec["commercial_use"] is False
    assert rec["redistribute"] is False
    assert rec["export_restricted"] is True


def test_unknown_family_blocks_commercial_use_and_export() -> None:
    with pytest.raises(PolicyDenied):
        check_licence("totally-novel-model", intended_use="commercial")
    with pytest.raises(PolicyDenied):
        check_export_control("totally-novel-model", destination="overseas")


def test_licence_for_matches_by_family_prefix() -> None:
    rec = licence_for("Llama-3-70B-Instruct")  # case-insensitive prefix match
    assert rec["licence_id"] == "llama-community"
    assert rec["commercial_use"] is True


def test_register_licence_extends_the_table() -> None:
    register_licence(
        "acme",
        LicenceRecord(
            name="ACME private",
            licence_id="acme-eula",
            commercial_use=False,
            redistribute=False,
            export_restricted=True,
        ),
    )
    try:
        rec = licence_for("acme-small")
        assert rec["licence_id"] == "acme-eula"
        with pytest.raises(PolicyDenied):
            check_licence("acme-small", intended_use="commercial")
    finally:
        from gadziriro.licensing.checks import LICENCE_TABLE

        LICENCE_TABLE.pop("acme", None)
