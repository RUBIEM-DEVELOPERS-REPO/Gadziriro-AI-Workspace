"""Model cards (FR-36).

A *model card* is a human-readable fact sheet for a trained model version: what
base model it derives from, its licence, the training data it saw (and how
sensitive that data is), the hyper-parameters and hardware that produced it, any
test scores, and the known limitations a reader must weigh before using it.

The card is assembled from facts the workspace already records — the model's
:class:`~gadziriro.registry.base.LineageRecord` plus the
:class:`~gadziriro.registry.base.DatasetVersion` each training reference resolves
to — so it never invents provenance. An optional
:class:`~gadziriro.evaluation.base.EvalResult` contributes measured scores.

Cards can be rendered to Markdown and persisted back into the object store under
``model_cards/<name>/<version>.md`` so they travel with the artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..core.errors import NotFound
from ..core.objectstore import ObjectStore
from ..evaluation.base import EvalResult
from ..governance.labels import SensitivityLabel
from ..registry.store import ObjectStoreRegistry

_CARDS = "model_cards"


@dataclass(frozen=True)
class TrainingDataRef:
    """One training dataset the model saw, with its sensitivity label."""

    ref: str  # pinned dataset reference, e.g. "patients@3"
    sensitivity: SensitivityLabel  # resolved from the registry, or a default
    resolved: bool = True  # False when the ref could not be resolved


@dataclass(frozen=True)
class ModelCard:
    """A readable fact sheet for one model version (FR-36)."""

    model_ref: str
    base_model: str
    licence: str
    training_data: tuple[TrainingDataRef, ...]
    hyperparams: dict[str, Any]
    hardware: str
    test_scores: dict[str, float]
    known_limits: tuple[str, ...]
    created_at: str


def build_model_card(
    registry: ObjectStoreRegistry,
    model_ref: str,
    *,
    licence: str = "unknown",
    eval_result: Optional[EvalResult] = None,
    known_limits: Optional[list[str]] = None,
) -> ModelCard:
    """Build a :class:`ModelCard` for ``model_ref`` from recorded facts.

    ``model_ref`` is either a bare model name (latest version) or a pinned
    ``name@version`` reference. Lineage (dataset refs, params, hardware) is read
    from the model version; each dataset reference is resolved to its sensitivity
    via the registry (unresolvable refs are kept and marked). ``base_model`` is
    derived from ``lineage.params`` (``base_model`` / ``base`` keys) when present.
    Test scores come from ``eval_result`` when supplied.

    Raises :class:`~gadziriro.core.errors.NotFound` if the model does not exist.
    """
    name, version = _split_ref(model_ref)
    model = registry.get_model(name, version)
    lineage = model.lineage

    training_data = tuple(
        _resolve_training_ref(registry, ref) for ref in lineage.dataset_refs
    )

    base_model = _derive_base_model(lineage.params)

    test_scores: dict[str, float] = {}
    if eval_result is not None:
        test_scores[eval_result.suite] = eval_result.score

    limits = tuple(known_limits or [])

    return ModelCard(
        model_ref=model.ref,
        base_model=base_model,
        licence=licence,
        training_data=training_data,
        hyperparams=dict(lineage.params),
        hardware=lineage.hardware,
        test_scores=test_scores,
        known_limits=limits,
        created_at=model.created_at,
    )


def render_markdown(card: ModelCard) -> str:
    """Render ``card`` as a readable Markdown fact sheet.

    The output names the licence, training data (with per-dataset sensitivity),
    hyper-parameters, hardware, any test scores, and the known limitations.
    """
    lines: list[str] = []
    lines.append(f"# Model Card: {card.model_ref}")
    lines.append("")
    lines.append(f"- **Base model:** {card.base_model}")
    lines.append(f"- **Licence:** {card.licence}")
    lines.append(f"- **Hardware:** {card.hardware or 'unspecified'}")
    lines.append(f"- **Created:** {card.created_at}")
    lines.append("")

    lines.append("## Training data")
    if card.training_data:
        for td in card.training_data:
            suffix = "" if td.resolved else " (unresolved)"
            lines.append(
                f"- `{td.ref}` — sensitivity: " f"**{td.sensitivity.value}**{suffix}"
            )
    else:
        lines.append("- _none recorded_")
    lines.append("")

    lines.append("## Hyper-parameters")
    if card.hyperparams:
        for key in sorted(card.hyperparams):
            lines.append(f"- `{key}` = `{card.hyperparams[key]}`")
    else:
        lines.append("- _none recorded_")
    lines.append("")

    lines.append("## Test scores")
    if card.test_scores:
        for suite in sorted(card.test_scores):
            lines.append(f"- **{suite}:** {card.test_scores[suite]:.4f}")
    else:
        lines.append("- _not evaluated_")
    lines.append("")

    lines.append("## Known limitations")
    if card.known_limits:
        for limit in card.known_limits:
            lines.append(f"- {limit}")
    else:
        lines.append("- _none documented_")
    lines.append("")

    return "\n".join(lines)


def store_card(registry_store: ObjectStore, card: ModelCard) -> str:
    """Persist the rendered ``card`` as Markdown in the object store.

    The card is written under ``model_cards/<name>/<version>.md`` and the key is
    returned. ``registry_store`` is the same object store the registry uses
    (e.g. a :class:`~gadziriro.core.objectstore.LocalObjectStore`).
    """
    name, version = _split_ref(card.model_ref)
    key = f"{_CARDS}/{name}/{version}.md"
    registry_store.put(key, render_markdown(card).encode("utf-8"))
    return key


# --------------------------------------------------------------------------- #
# internals
# --------------------------------------------------------------------------- #
def _split_ref(model_ref: str) -> tuple[str, Optional[int]]:
    """Split ``name@version`` into (name, version); bare name -> (name, None)."""
    name, sep, version = model_ref.rpartition("@")
    if not sep:
        return model_ref, None
    try:
        return name, int(version)
    except ValueError:
        # "@" present but not a version suffix — treat whole string as a name.
        return model_ref, None


def _resolve_training_ref(registry: ObjectStoreRegistry, ref: str) -> TrainingDataRef:
    """Resolve a dataset ``ref`` to its sensitivity, defaulting strict on miss."""
    name, sep, version = ref.rpartition("@")
    if sep:
        try:
            dataset = registry.get_dataset(name, int(version))
            return TrainingDataRef(ref=ref, sensitivity=dataset.sensitivity)
        except (NotFound, ValueError):
            pass
    # Unresolvable reference: assume the strictest label by default (BRD §18).
    return TrainingDataRef(ref=ref, sensitivity=SensitivityLabel.PHI, resolved=False)


def _derive_base_model(params: dict[str, Any]) -> str:
    """Derive the base model name from lineage params, or 'unknown'."""
    for key in ("base_model", "base", "foundation_model"):
        value = params.get(key)
        if value:
            return str(value)
    return "unknown"
