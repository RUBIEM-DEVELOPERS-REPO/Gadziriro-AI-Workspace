"""Model-card routes (FR-36) — build + render a model version's fact sheet.

``GET /api/modelcards/{name}/{version}`` builds a model card from the recorded
lineage/datasets, renders it to Markdown, and (optionally, ``?store=true``)
persists it into the shared object store. Every route requires an authenticated
principal.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from ...auth.base import Principal
from ...modelcards.card import ModelCard, build_model_card, render_markdown, store_card
from ...registry.store import ObjectStoreRegistry
from ..deps import get_current_principal, get_object_store, get_registry
from ..registry import register_router

router = APIRouter(tags=["modelcards"])


def _card_to_dict(card: ModelCard) -> dict[str, Any]:
    """Project a :class:`ModelCard` onto a JSON-serialisable dict."""
    return {
        "model_ref": card.model_ref,
        "base_model": card.base_model,
        "licence": card.licence,
        "training_data": [
            {
                "ref": td.ref,
                "sensitivity": td.sensitivity.value,
                "resolved": td.resolved,
            }
            for td in card.training_data
        ],
        "hyperparams": dict(card.hyperparams),
        "hardware": card.hardware,
        "test_scores": dict(card.test_scores),
        "known_limits": list(card.known_limits),
        "created_at": card.created_at,
    }


@router.get("/{name}/{version}")
def get_model_card(
    name: str,
    version: int,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    store: Annotated[Any, Depends(get_object_store)],
    _: Annotated[Principal, Depends(get_current_principal)],
    licence: str = "unknown",
    store_card_flag: bool = False,
) -> dict[str, Any]:
    """Build + render a model card, optionally persisting it (FR-36).

    ``licence`` sets the card's stated licence; ``store_card_flag`` (query
    ``store_card_flag=true``) also writes the rendered card to the object store.

    :raises NotFound: if the model/version does not exist (404).
    """
    card = build_model_card(registry, f"{name}@{version}", licence=licence)
    markdown = render_markdown(card)

    stored_key = store_card(store, card) if store_card_flag else None
    return {
        "card": _card_to_dict(card),
        "markdown": markdown,
        "stored_key": stored_key,
    }


register_router("/api/modelcards", router)
