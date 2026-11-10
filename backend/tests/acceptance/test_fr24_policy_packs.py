"""Acceptance tests for FR-24 — one-switch compliance policy packs.

FR-24 / BRD §18: enabling several compliance packs produces a single effective
policy in which, field by field, the *strictest common setting wins*, and the
precedence (which pack set each value) is recorded for the UI and audit log.
"""

from __future__ import annotations

from gadziriro.governance.labels import SensitivityLabel
from gadziriro.policy.packs import (
    BASELINE_SOURCE,
    PolicySettings,
    describe_precedence,
    merge_packs,
)

ALL_PACKS = ["hipaa", "gdpr", "soc2", "zw-dpa"]


def test_all_packs_merge_to_one_strictest_effective_policy() -> None:
    """hipaa+gdpr+soc2+zw-dpa collapse to one strictest-wins policy (BRD §18)."""
    eff = merge_packs(ALL_PACKS)
    s = eff.settings

    assert isinstance(s, PolicySettings)
    # Default-deny network egress survives the merge.
    assert s.allow_egress is False
    # MFA is mandatory because at least one pack requires it.
    assert s.require_mfa is True
    # No pack permits cross-border transfer -> forbidden.
    assert s.cross_border_transfer_allowed is False
    # Audit retention: the maximum (strictest) across packs -> HIPAA's 6 years.
    assert s.audit_retention_days == 2190
    # Data retention: the minimum (strictest) across packs -> GDPR's 365 days.
    assert s.data_retention_max_days == 365
    # Idle session timeout: the minimum (strictest) -> HIPAA's 15 minutes.
    assert s.min_session_timeout_s == 900
    # Export approval labels: the union across packs -> personal data AND PHI.
    assert s.export_approval_labels == frozenset(
        {SensitivityLabel.PERSONAL, SensitivityLabel.PHI}
    )


def test_precedence_is_recorded_for_the_merged_policy() -> None:
    """The provenance map names the winning pack for each effective control."""
    eff = merge_packs(ALL_PACKS)
    prov = eff.provenance

    assert prov == describe_precedence(ALL_PACKS)

    # The strictest numeric winners are attributed to the right regimes.
    assert prov["audit_retention_days"] == "hipaa"
    assert prov["data_retention_max_days"] == "gdpr"
    assert prov["min_session_timeout_s"] == "hipaa"
    # MFA + cross-border: the first enabled pack asserting the strict value.
    assert prov["require_mfa"] == "hipaa"
    assert prov["cross_border_transfer_allowed"] == "hipaa"
    # Export-approval union credits every contributing pack (SOC 2 adds none).
    assert prov["export_approval_labels"] == ["hipaa", "gdpr", "zw-dpa"]


def test_enabling_order_is_preserved_but_outcome_is_stable() -> None:
    """Order changes provenance choices but never the strictest effective value."""
    forward = merge_packs(ALL_PACKS)
    reverse = merge_packs(list(reversed(ALL_PACKS)))

    # The strictest-wins settings are identical regardless of enablement order.
    assert forward.settings == reverse.settings
    # Order is remembered for display.
    assert reverse.enabled == ("zw-dpa", "soc2", "gdpr", "hipaa")
    # Baseline is never the source once any pack tightens a control.
    assert forward.provenance["require_mfa"] != BASELINE_SOURCE
