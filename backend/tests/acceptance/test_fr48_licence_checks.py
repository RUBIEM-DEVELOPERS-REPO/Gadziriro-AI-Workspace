"""Acceptance test: licence + export-control checks (FR-48).

Licence and export-control checks block a disallowed use or export BEFORE the
model is used or shipped — the gate the requirement describes.
"""

from __future__ import annotations

import pytest

from gadziriro.core.errors import PolicyDenied
from gadziriro.licensing import check_export_control, check_licence, licence_for


def test_fr48_licence_gate_blocks_before_use() -> None:
    # A non-commercial model cannot be used commercially: the gate raises
    # before any use happens.
    with pytest.raises(PolicyDenied):
        check_licence("research-13b", intended_use="commercial")

    # A permissive, commercial-friendly model passes the gate.
    check_licence("llama-3-8b", intended_use="commercial")


def test_fr48_export_gate_blocks_before_export() -> None:
    # An export-restricted model to a disallowed destination is blocked.
    with pytest.raises(PolicyDenied):
        check_export_control("qwen2-72b", destination="overseas")

    # The same model to an allowed destination is permitted.
    check_export_control("qwen2-72b", destination="domestic")

    # An unrestricted model exports anywhere.
    check_export_control("mistral-7b", destination="overseas")


def test_fr48_unknown_model_is_restricted_by_default() -> None:
    # Unknown families default to the strictest posture so nothing slips through.
    rec = licence_for("mystery-model-1")
    assert rec["commercial_use"] is False
    assert rec["export_restricted"] is True

    with pytest.raises(PolicyDenied):
        check_licence("mystery-model-1", intended_use="commercial")
    with pytest.raises(PolicyDenied):
        check_export_control("mystery-model-1", destination="overseas")
