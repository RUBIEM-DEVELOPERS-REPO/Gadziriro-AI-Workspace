"""Compliance policy-pack routes (FR-24).

``GET /api/policy/packs`` lists the available one-switch compliance packs;
``POST /api/policy/packs/effective`` merges a set of enabled packs into one
strictest-wins effective policy and returns both the resolved settings and the
provenance (which pack set each control). Every route requires an authenticated
principal.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...auth.base import Principal
from ...policy.packs import (
    PACKS,
    EffectiveSettings,
    PolicyPack,
    PolicySettings,
    describe_precedence,
    merge_packs,
)
from ..deps import get_current_principal
from ..registry import register_router

router = APIRouter(tags=["policypacks"])


class EffectiveIn(BaseModel):
    """Body for computing an effective policy from enabled packs."""

    enabled: list[str] = Field(default_factory=list)


def _settings_to_dict(settings: PolicySettings) -> dict[str, Any]:
    """Project :class:`PolicySettings` onto a JSON-serialisable dict."""
    return {
        "allow_egress": settings.allow_egress,
        "require_mfa": settings.require_mfa,
        "audit_retention_days": settings.audit_retention_days,
        "data_retention_max_days": settings.data_retention_max_days,
        "export_approval_labels": sorted(
            label.value for label in settings.export_approval_labels
        ),
        "min_session_timeout_s": settings.min_session_timeout_s,
        "cross_border_transfer_allowed": settings.cross_border_transfer_allowed,
    }


def _pack_to_dict(pack: PolicyPack) -> dict[str, Any]:
    """Project a :class:`PolicyPack` onto a JSON-serialisable dict."""
    return {
        "name": pack.name,
        "title": pack.title,
        "settings": _settings_to_dict(pack.settings),
    }


def _effective_to_dict(effective: EffectiveSettings) -> dict[str, Any]:
    """Project :class:`EffectiveSettings` (settings + provenance) onto a dict."""
    return {
        "settings": _settings_to_dict(effective.settings),
        "provenance": dict(effective.provenance),
        "enabled": list(effective.enabled),
    }


@router.get("/packs")
def list_packs(
    _: Annotated[Principal, Depends(get_current_principal)],
) -> list[dict[str, Any]]:
    """List every available compliance policy pack (FR-24)."""
    return [_pack_to_dict(pack) for pack in PACKS.values()]


@router.post("/packs/effective")
def effective(
    body: EffectiveIn,
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Merge enabled packs into a strictest-wins effective policy (FR-24).

    :raises ConfigError: if a pack name is unknown (mapped to HTTP 400).
    """
    merged = merge_packs(body.enabled)
    out = _effective_to_dict(merged)
    out["precedence"] = describe_precedence(body.enabled)
    return out


register_router("/api/policy", router)
