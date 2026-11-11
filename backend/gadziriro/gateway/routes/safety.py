"""Model safety checks (FR-37) — data scientist or admin.

* ``POST /api/safety/bias`` — group-disparity check.
* ``POST /api/safety/redteam`` — red-team prompt suite.

Both use the default deterministic answer function (no live inference).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...auth.base import Principal, Role
from ...redteam.bias import BiasTestItem, run_bias_check
from ...redteam.redteam import run_red_team
from ..deps import require_any_role
from ..registry import register_router

router = APIRouter(tags=["safety"])

_require_ds_or_admin = require_any_role(Role.DATA_SCIENTIST, Role.ADMIN)


class BiasItemIn(BaseModel):
    """One bias test item: a template with a ``{group}`` slot + groups."""

    template: str
    groups: list[str]


class BiasIn(BaseModel):
    """Body for a bias check."""

    model_ref: str
    items: list[BiasItemIn]
    threshold: float = Field(default=0.1, ge=0.0, le=1.0)


class RedTeamIn(BaseModel):
    """Body for a red-team run."""

    model_ref: str


@router.post("/bias")
def bias_check(
    body: BiasIn,
    _: Annotated[Principal, Depends(_require_ds_or_admin)],
) -> dict[str, Any]:
    """Run a bias check and return pass/fail plus per-item detail."""
    items = [BiasTestItem(i.template, tuple(i.groups)) for i in body.items]
    result = run_bias_check(body.model_ref, items, threshold=body.threshold)
    return {
        "model_ref": result.model_ref,
        "passed": result.passed,
        "disparity": result.disparity,
        "per_item": list(result.per_item),
    }


@router.post("/redteam")
def redteam(
    body: RedTeamIn,
    _: Annotated[Principal, Depends(_require_ds_or_admin)],
) -> dict[str, Any]:
    """Run the red-team suite and return pass/fail plus flagged answers."""
    result = run_red_team(body.model_ref)
    return {
        "model_ref": result.model_ref,
        "passed": result.passed,
        "total": result.total,
        "unsafe": list(result.unsafe),
    }


register_router("/api/safety", router)
