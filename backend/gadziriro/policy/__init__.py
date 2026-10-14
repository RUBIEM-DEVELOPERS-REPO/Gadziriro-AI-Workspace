"""Policy engine.

Phase 0 enforces the egress gate (:mod:`gadziriro.policy.egress`); Phase 1 adds
export approval (:mod:`gadziriro.policy.exports`); Phase 2 adds one-switch
compliance packs (:mod:`gadziriro.policy.packs`, FR-24).
"""

from __future__ import annotations

from .packs import (
    BASELINE,
    PACKS,
    EffectiveSettings,
    PolicyPack,
    PolicySettings,
    describe_precedence,
    merge_packs,
)

__all__ = [
    "BASELINE",
    "PACKS",
    "EffectiveSettings",
    "PolicyPack",
    "PolicySettings",
    "describe_precedence",
    "merge_packs",
]
