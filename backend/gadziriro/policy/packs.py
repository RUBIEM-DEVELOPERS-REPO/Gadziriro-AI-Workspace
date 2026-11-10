"""Compliance policy packs (FR-24).

A *policy pack* is a one-switch bundle of concrete tightening settings for a
regulatory regime (HIPAA, GDPR, SOC 2, Zimbabwe DPA). Enabling a pack applies
its settings; enabling several merges them so that, per BRD §18, the **strictest
common setting wins** for every field. A pack can only ever *tighten* the
effective policy relative to a safe default baseline (egress off, no cross-border
transfers, nothing auto-exported) -- it can never loosen it.

The merge is deterministic and fully auditable: :class:`EffectiveSettings`
records both the winning value for each field *and* which pack set it (a
provenance map), so the UI and the audit log can show exactly why a given
control is in force.

Strictness direction is defined per field:

* booleans -- the more restrictive value wins (``allow_egress`` /
  ``cross_border_transfer_allowed`` strict-False via AND; ``require_mfa``
  strict-True via OR);
* ``audit_retention_days`` -- higher is stricter, so the maximum wins;
* ``data_retention_max_days`` / ``min_session_timeout_s`` -- lower is stricter,
  so the minimum wins;
* ``export_approval_labels`` -- the union wins (requiring approval for *more*
  labels is stricter).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Union

from ..core.errors import ConfigError
from ..governance.labels import SensitivityLabel

__all__ = [
    "PolicySettings",
    "PolicyPack",
    "EffectiveSettings",
    "BASELINE",
    "PACKS",
    "merge_packs",
    "describe_precedence",
    "BASELINE_SOURCE",
]

# Provenance value: the name of the single pack that set a scalar field, the
# sentinel :data:`BASELINE_SOURCE` when no enabled pack tightened it, or the
# list of packs that contributed to a set-valued (union) field.
Provenance = Union[str, list]

# Sentinel recorded in a provenance map when the safe baseline value stands
# because no enabled pack asserted the winning value.
BASELINE_SOURCE = "baseline"


@dataclass(frozen=True)
class PolicySettings:
    """Concrete, comparable compliance settings (FR-24).

    Each field has a defined strictness direction (see the module docstring).
    Instances are frozen so a pack's declared settings cannot be mutated after
    registration.

    Attributes:
        allow_egress: Whether outbound network egress is permitted at all.
            Default-deny; stricter value is ``False``.
        require_mfa: Whether multi-factor authentication is mandatory. Stricter
            value is ``True``.
        audit_retention_days: Minimum days audit records must be retained.
            Higher is stricter.
        data_retention_max_days: Maximum days ordinary data may be retained
            before deletion. Lower is stricter (data minimisation).
        export_approval_labels: Sensitivity labels whose export requires human
            approval. The union across packs is stricter.
        min_session_timeout_s: Idle session timeout in seconds. Lower is
            stricter.
        cross_border_transfer_allowed: Whether data may be transferred across a
            national border. Stricter value is ``False``.
    """

    allow_egress: bool = False
    require_mfa: bool = False
    audit_retention_days: int = 0
    data_retention_max_days: int = 36500
    export_approval_labels: frozenset[SensitivityLabel] = field(
        default_factory=frozenset
    )
    min_session_timeout_s: int = 86400
    cross_border_transfer_allowed: bool = False


# How each field of :class:`PolicySettings` is reduced to its strictest value.
#   "and"   -> False wins (restrictive boolean, default-deny)
#   "or"    -> True wins  (restrictive boolean, mandatory control)
#   "max"   -> larger wins (higher = stricter)
#   "min"   -> smaller wins (lower = stricter)
#   "union" -> set union  (more labels in scope = stricter)
_STRATEGY: dict[str, str] = {
    "allow_egress": "and",
    "require_mfa": "or",
    "audit_retention_days": "max",
    "data_retention_max_days": "min",
    "export_approval_labels": "union",
    "min_session_timeout_s": "min",
    "cross_border_transfer_allowed": "and",
}


@dataclass(frozen=True)
class PolicyPack:
    """A named, one-switch compliance pack (FR-24).

    Attributes:
        name: The pack's switch name (e.g. ``"hipaa"``).
        title: Human-readable regime name for display.
        settings: The concrete tightening settings the pack applies.
    """

    name: str
    title: str
    settings: PolicySettings


@dataclass(frozen=True)
class EffectiveSettings:
    """The merged, strictest-wins policy plus its provenance (BRD §18).

    Attributes:
        settings: The resolved :class:`PolicySettings` where each field holds
            the strictest value across the enabled packs and the baseline.
        provenance: Map of field name to the pack that set the winning value
            (:data:`BASELINE_SOURCE` if none tightened it; a list of contributing
            packs for the union-valued ``export_approval_labels``).
        enabled: The packs that were merged, in the order supplied.
    """

    settings: PolicySettings
    provenance: dict[str, Provenance]
    enabled: tuple[str, ...]


# The safe default baseline: an empty-list merge resolves to exactly this, so an
# unconfigured workspace is still locked down (no egress, no cross-border
# transfer, MFA not yet forced but nothing exportable and effectively unbounded
# retention windows that any pack can only tighten).
BASELINE = PolicySettings()


# ---------------------------------------------------------------------------
# Pack registry
# ---------------------------------------------------------------------------

# HIPAA: protected health information. No egress, no cross-border transfer, MFA
# mandatory, a long (6-year) audit retention window, short idle sessions, and
# approval for personal data and PHI exports.
_HIPAA = PolicyPack(
    name="hipaa",
    title="HIPAA (US protected health information)",
    settings=PolicySettings(
        allow_egress=False,
        require_mfa=True,
        audit_retention_days=2190,
        data_retention_max_days=2190,
        export_approval_labels=frozenset(
            {SensitivityLabel.PERSONAL, SensitivityLabel.PHI}
        ),
        min_session_timeout_s=900,
        cross_border_transfer_allowed=False,
    ),
)

# GDPR: EU personal data. Data minimisation (short data-retention cap), DSAR /
# export approval for PERSONAL data, MFA, and no cross-border transfer by
# default.
_GDPR = PolicyPack(
    name="gdpr",
    title="GDPR (EU personal data)",
    settings=PolicySettings(
        allow_egress=False,
        require_mfa=True,
        audit_retention_days=365,
        data_retention_max_days=365,
        export_approval_labels=frozenset({SensitivityLabel.PERSONAL}),
        min_session_timeout_s=1800,
        cross_border_transfer_allowed=False,
    ),
)

# SOC 2: security/availability controls. Emphasis on audit retention, MFA and
# change control rather than data-residency; it does not itself forbid
# cross-border transfer, but the merge still never loosens a stricter pack.
_SOC2 = PolicyPack(
    name="soc2",
    title="SOC 2 (trust services criteria)",
    settings=PolicySettings(
        allow_egress=False,
        require_mfa=True,
        audit_retention_days=365,
        data_retention_max_days=2555,
        export_approval_labels=frozenset(),
        min_session_timeout_s=3600,
        cross_border_transfer_allowed=True,
    ),
)

# ZW-DPA: Zimbabwe Data Protection Act. Like GDPR it protects personal data and
# forbids cross-border transfer, requires MFA, and caps data retention.
_ZW_DPA = PolicyPack(
    name="zw-dpa",
    title="Zimbabwe Data Protection Act",
    settings=PolicySettings(
        allow_egress=False,
        require_mfa=True,
        audit_retention_days=1825,
        data_retention_max_days=1095,
        export_approval_labels=frozenset({SensitivityLabel.PERSONAL}),
        min_session_timeout_s=1200,
        cross_border_transfer_allowed=False,
    ),
)

#: Registry of every available pack, keyed by switch name.
PACKS: dict[str, PolicyPack] = {
    _HIPAA.name: _HIPAA,
    _GDPR.name: _GDPR,
    _SOC2.name: _SOC2,
    _ZW_DPA.name: _ZW_DPA,
}


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def _resolve(name: str) -> PolicyPack:
    """Return the pack named ``name`` or raise :class:`ConfigError`.

    Names are matched case-insensitively after stripping surrounding
    whitespace.
    """
    key = name.strip().lower()
    try:
        return PACKS[key]
    except KeyError as exc:
        known = ", ".join(sorted(PACKS))
        raise ConfigError(f"unknown policy pack: {name!r} (known: {known})") from exc


def _reduce_scalar(strategy: str, values: list) -> object:
    """Reduce ``values`` to the strictest one under ``strategy``."""
    if strategy == "and":
        return all(values)
    if strategy == "or":
        return any(values)
    if strategy == "max":
        return max(values)
    if strategy == "min":
        return min(values)
    raise ConfigError(f"unknown scalar strategy: {strategy!r}")


def merge_packs(enabled: list[str]) -> EffectiveSettings:
    """Merge ``enabled`` packs into one strictest-wins policy (BRD §18).

    Starts from the safe :data:`BASELINE` so an empty list resolves to a fully
    locked-down policy. For each field the strictest value across the baseline
    and every enabled pack wins, and the provenance map names the pack that set
    it (or :data:`BASELINE_SOURCE` when no pack tightened it).

    Args:
        enabled: Pack switch names, in precedence-display order. Case and
            surrounding whitespace are ignored.

    Returns:
        The merged :class:`EffectiveSettings`.

    Raises:
        ConfigError: if any name is not a known pack.
    """
    packs = [_resolve(name) for name in enabled]

    resolved: dict[str, object] = {}
    provenance: dict[str, Provenance] = {}

    for fname, strategy in _STRATEGY.items():
        base_val = getattr(BASELINE, fname)

        if strategy == "union":
            winning: set[SensitivityLabel] = set(base_val)
            contributors: list[str] = []
            for pack in packs:
                pack_val = getattr(pack.settings, fname)
                if pack_val:
                    winning |= set(pack_val)
                    contributors.append(pack.name)
            resolved[fname] = frozenset(winning)
            provenance[fname] = contributors if contributors else BASELINE_SOURCE
            continue

        candidates = [base_val] + [getattr(p.settings, fname) for p in packs]
        winner = _reduce_scalar(strategy, candidates)
        resolved[fname] = winner

        # The winning pack is the first enabled one that asserts the winning
        # value; otherwise the baseline stands.
        source: str = BASELINE_SOURCE
        for pack in packs:
            if getattr(pack.settings, fname) == winner:
                source = pack.name
                break
        provenance[fname] = source

    settings = PolicySettings(**resolved)  # type: ignore[arg-type]
    return EffectiveSettings(
        settings=settings,
        provenance=provenance,
        enabled=tuple(p.name for p in packs),
    )


def describe_precedence(enabled: list[str]) -> dict[str, Provenance]:
    """Return the provenance map for ``enabled`` packs (BRD §18).

    This is the ``field -> pack`` map that the UI and audit log use to explain
    which pack set each effective control. It covers every field of
    :class:`PolicySettings`.

    Args:
        enabled: Pack switch names, in precedence-display order.

    Returns:
        A fresh provenance map (a copy, safe for the caller to mutate).

    Raises:
        ConfigError: if any name is not a known pack.
    """
    provenance = merge_packs(enabled).provenance
    # Guard against an accidentally missing field as the dataclass evolves.
    expected = {f.name for f in fields(PolicySettings)}
    missing = expected - set(provenance)
    if missing:  # pragma: no cover - defensive
        raise ConfigError(f"provenance missing fields: {sorted(missing)}")
    return dict(provenance)
