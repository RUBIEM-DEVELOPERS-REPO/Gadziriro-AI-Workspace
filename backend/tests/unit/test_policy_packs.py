"""Unit tests for compliance policy packs (FR-24, BRD §18)."""

from __future__ import annotations

import pytest

from gadziriro.core.errors import ConfigError
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.policy.packs import (
    BASELINE,
    BASELINE_SOURCE,
    PACKS,
    PolicyPack,
    PolicySettings,
    describe_precedence,
    merge_packs,
)


def test_all_four_packs_exist_with_expected_key_settings() -> None:
    """The four regimes are registered with their characteristic tightening."""
    assert set(PACKS) == {"hipaa", "gdpr", "soc2", "zw-dpa"}
    for pack in PACKS.values():
        assert isinstance(pack, PolicyPack)
        assert isinstance(pack.settings, PolicySettings)
        # Every pack forbids egress by default and mandates MFA.
        assert pack.settings.allow_egress is False
        assert pack.settings.require_mfa is True

    hipaa = PACKS["hipaa"].settings
    assert hipaa.cross_border_transfer_allowed is False
    assert hipaa.audit_retention_days == 2190  # 6-year window, the strictest
    assert SensitivityLabel.PHI in hipaa.export_approval_labels
    assert hipaa.min_session_timeout_s == 900  # the shortest session

    gdpr = PACKS["gdpr"].settings
    assert gdpr.cross_border_transfer_allowed is False
    assert gdpr.data_retention_max_days == 365  # data minimisation, the lowest
    assert gdpr.export_approval_labels == frozenset({SensitivityLabel.PERSONAL})

    soc2 = PACKS["soc2"].settings
    assert soc2.audit_retention_days >= 365  # audit-retention emphasis

    zw = PACKS["zw-dpa"].settings
    assert zw.cross_border_transfer_allowed is False
    assert SensitivityLabel.PERSONAL in zw.export_approval_labels


def test_empty_merge_returns_safe_baseline() -> None:
    """merge_packs([]) resolves to exactly the safe baseline, provenance baseline."""
    eff = merge_packs([])
    assert eff.settings == BASELINE
    assert eff.enabled == ()
    assert eff.settings.allow_egress is False
    assert eff.settings.cross_border_transfer_allowed is False
    assert eff.settings.export_approval_labels == frozenset()
    # Nothing tightened anything -> every field attributed to the baseline.
    assert set(eff.provenance.values()) == {BASELINE_SOURCE}


def test_merge_takes_stricter_numeric_values() -> None:
    """Across two packs the smaller data-retention cap and larger audit win."""
    eff = merge_packs(["hipaa", "gdpr"])
    s = eff.settings
    # data_retention_max_days: lower is stricter -> GDPR's 365.
    assert s.data_retention_max_days == 365
    assert eff.provenance["data_retention_max_days"] == "gdpr"
    # audit_retention_days: higher is stricter -> HIPAA's 2190.
    assert s.audit_retention_days == 2190
    assert eff.provenance["audit_retention_days"] == "hipaa"
    # min_session_timeout_s: lower is stricter -> HIPAA's 900.
    assert s.min_session_timeout_s == 900
    assert eff.provenance["min_session_timeout_s"] == "hipaa"


def test_merge_unions_export_approval_labels_with_provenance() -> None:
    """The union of approval labels wins and every contributor is recorded."""
    eff = merge_packs(["gdpr", "hipaa"])
    assert eff.settings.export_approval_labels == frozenset(
        {SensitivityLabel.PERSONAL, SensitivityLabel.PHI}
    )
    # Both packs contribute at least one label to the union.
    assert eff.provenance["export_approval_labels"] == ["gdpr", "hipaa"]


def test_require_mfa_true_if_any_pack_requires_it() -> None:
    """A single pack flips MFA on relative to the baseline."""
    assert BASELINE.require_mfa is False
    eff = merge_packs(["soc2"])
    assert eff.settings.require_mfa is True
    assert eff.provenance["require_mfa"] == "soc2"


def test_cross_border_false_if_any_pack_forbids_it() -> None:
    """A permissive pack cannot loosen; a forbidding pack is credited."""
    # SOC 2 alone would permit cross-border, but the baseline keeps it False.
    only_soc2 = merge_packs(["soc2"])
    assert only_soc2.settings.cross_border_transfer_allowed is False
    assert only_soc2.provenance["cross_border_transfer_allowed"] == BASELINE_SOURCE

    # Add HIPAA, which forbids it: the forbidding pack now sets the value.
    with_hipaa = merge_packs(["soc2", "hipaa"])
    assert with_hipaa.settings.cross_border_transfer_allowed is False
    assert with_hipaa.provenance["cross_border_transfer_allowed"] == "hipaa"


def test_describe_precedence_covers_every_field() -> None:
    """The provenance map names a source for every policy field."""
    prov = describe_precedence(["hipaa", "gdpr"])
    for fname in (
        "allow_egress",
        "require_mfa",
        "audit_retention_days",
        "data_retention_max_days",
        "export_approval_labels",
        "min_session_timeout_s",
        "cross_border_transfer_allowed",
    ):
        assert fname in prov


def test_unknown_pack_raises_config_error() -> None:
    """An unrecognised pack name is a configuration error."""
    with pytest.raises(ConfigError):
        merge_packs(["hipaa", "nonexistent"])
    with pytest.raises(ConfigError):
        describe_precedence(["pci-dss"])


def test_pack_names_are_case_insensitive() -> None:
    """Switch names tolerate case and surrounding whitespace."""
    eff = merge_packs([" HIPAA ", "GDPR"])
    assert eff.enabled == ("hipaa", "gdpr")
