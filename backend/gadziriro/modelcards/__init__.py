"""Gadziriro modelcards (Phase 2 Model Studio).

Model cards (FR-36): human-readable fact sheets assembled from a model
version's recorded lineage, datasets, evaluation scores and known limits.
"""

from .card import (
    ModelCard,
    TrainingDataRef,
    build_model_card,
    render_markdown,
    store_card,
)

__all__ = [
    "ModelCard",
    "TrainingDataRef",
    "build_model_card",
    "render_markdown",
    "store_card",
]
