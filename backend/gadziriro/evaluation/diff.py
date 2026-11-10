"""Model diff (FR-13): compare two model versions and summarise weight changes.

:func:`model_diff` is :func:`gadziriro.evaluation.harness.compare` plus a
simulated *weight-change summary* derived from the two versions' stored
checksums (and a checksum-derived simulated byte size). It stays deterministic
and never touches real model weights: the summary reports whether the content
checksum changed and an approximate fraction of weights that "moved".

When no ``suite`` is given, the scores default to ``0`` and only the weight
summary is populated — the "just show me what changed on disk" view.
"""

from __future__ import annotations

from typing import Optional

from .. import governance as _governance  # noqa: F401  (init governance first)
from ..registry.base import ModelVersion
from ..registry.store import ObjectStoreRegistry
from .base import ComparisonResult, EvalItem
from .harness import AnswerFn, _resolve_model, compare


def _simulated_bytes(checksum: str) -> int:
    """Return a stable, simulated weight size (in bytes) for ``checksum``.

    Derived from the checksum so identical content yields an identical size and
    different content yields a different one — deterministic, no real file read.
    """
    return int(checksum[:12], 16)


def _changed_fraction(checksum_a: str, checksum_b: str) -> float:
    """Return the fraction of differing hex digits between two checksums.

    Used as a simulated "fraction of weights that changed" between versions:
    ``0.0`` for identical content, up to ``1.0`` for fully different digests.
    """
    if checksum_a == checksum_b:
        return 0.0
    pairs = list(zip(checksum_a, checksum_b, strict=False))
    if not pairs:
        return 0.0
    differing = sum(1 for x, y in pairs if x != y)
    return differing / len(pairs)


def _weight_summary(model_a: ModelVersion, model_b: ModelVersion) -> dict[str, object]:
    """Build the FR-13 simulated weight-change summary for two versions."""
    return {
        "bytes_a": _simulated_bytes(model_a.checksum),
        "bytes_b": _simulated_bytes(model_b.checksum),
        "checksum_a": model_a.checksum,
        "checksum_b": model_b.checksum,
        "checksum_changed": model_a.checksum != model_b.checksum,
        "approx_changed_fraction": _changed_fraction(
            model_a.checksum, model_b.checksum
        ),
    }


def model_diff(
    registry: ObjectStoreRegistry,
    a_ref: str,
    b_ref: str,
    suite: Optional[list[EvalItem]] = None,
    answer_fn: Optional[AnswerFn] = None,
) -> ComparisonResult:
    """Diff model ``a_ref`` against ``b_ref`` (FR-13).

    Resolves both versions (each must exist, else
    :class:`~gadziriro.core.errors.NotFound`) and builds the weight-change
    summary from their checksums. When ``suite`` is provided it also runs the
    FR-11 side-by-side evaluation (scores + sample diffs); when it is ``None``
    the scores default to ``0`` and only the weight summary is returned.
    """
    model_a = _resolve_model(registry, a_ref)
    model_b = _resolve_model(registry, b_ref)
    summary = _weight_summary(model_a, model_b)

    if suite is None:
        return ComparisonResult(
            a_ref=a_ref,
            b_ref=b_ref,
            score_a=0.0,
            score_b=0.0,
            score_delta=0.0,
            sample_diffs=(),
            weight_summary=summary,
        )

    scored = compare(registry, a_ref, b_ref, suite, answer_fn=answer_fn)
    return ComparisonResult(
        a_ref=scored.a_ref,
        b_ref=scored.b_ref,
        score_a=scored.score_a,
        score_b=scored.score_b,
        score_delta=scored.score_delta,
        sample_diffs=scored.sample_diffs,
        weight_summary=summary,
    )
