"""Evaluation harness (FR-11): score a model version against a question set.

The harness is *mock-backed* and fully deterministic: there is no real model
inference. A model version "answers" a prompt through an injectable
``answer_fn``. The default answerer, :func:`default_answer_fn`, is a pure
function of ``(model_ref, prompt)`` that simulates a model whose competence
depends on its version, so two versions of the same model can (and do) score
differently on the same suite without any randomness.

Scoring is a weighted exact/normalised match of the answer against the item's
expected answer, aggregated to a ``0..1`` score. :func:`evaluate` produces an
:class:`~gadziriro.evaluation.base.EvalResult`; :func:`compare` runs two
versions over the *same* suite side by side into a
:class:`~gadziriro.evaluation.base.ComparisonResult` (FR-11 compare view).
"""

from __future__ import annotations

import hashlib
from typing import Callable, Optional

from .. import governance as _governance  # noqa: F401  (init governance first)
from ..registry.base import ModelVersion
from ..registry.store import ObjectStoreRegistry
from .base import ComparisonResult, EvalItem, EvalResult

#: An answerer maps ``(model_ref, prompt)`` to a (deterministic) answer string.
AnswerFn = Callable[[str, str], str]

#: How many ``(prompt, answer)`` samples to capture on an :class:`EvalResult`.
_SAMPLE_LIMIT = 3


def _digest(*parts: str) -> str:
    """Return a stable hex digest of ``parts`` (deterministic, no salt)."""
    joined = "\x00".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _parse_ref(model_ref: str) -> tuple[str, Optional[int]]:
    """Split ``"name@version"`` into ``(name, version)`` (``version`` may be None).

    A bare ``"name"`` resolves to the latest version (``version is None``). A
    non-integer version is returned as ``None`` name so resolution raises
    :class:`~gadziriro.core.errors.NotFound` via the registry.
    """
    name, sep, raw = model_ref.partition("@")
    if not sep:
        return model_ref, None
    try:
        return name, int(raw)
    except ValueError:
        # Force a NotFound from the registry for a malformed ref.
        return model_ref, None


def _resolve_model(registry: ObjectStoreRegistry, model_ref: str) -> ModelVersion:
    """Resolve ``model_ref`` to a :class:`ModelVersion` or raise ``NotFound``."""
    name, version = _parse_ref(model_ref)
    return registry.get_model(name, version)


def _normalise(text: str) -> str:
    """Normalise an answer for matching (casefold + collapse whitespace)."""
    return " ".join(text.strip().casefold().split())


# --------------------------------------------------------------------------- #
# deterministic mock "model"
# --------------------------------------------------------------------------- #
def _version_of(model_ref: str) -> int:
    """Return a stable positive version number inferred from ``model_ref``."""
    _, version = _parse_ref(model_ref)
    if version is not None and version > 0:
        return version
    # No usable explicit version: derive a stable 1..5 pseudo-version.
    return int(_digest(model_ref)[:4], 16) % 5 + 1


def _mistake_rate(model_ref: str) -> int:
    """Return this version's mistake rate as a percentage in ``[5, 45]``.

    Higher versions are modelled as more competent (lower mistake rate), which
    is what lets a newer version out-score an older one on the same suite.
    """
    version = _version_of(model_ref)
    return max(5, 45 - 10 * version)


def reference_answer(prompt: str) -> str:
    """Return the canonical (version-independent) answer for ``prompt``.

    This is the answer a fully competent model gives. It is the natural ground
    truth to use when building an :class:`EvalItem.expected` for a mock-backed
    suite, so a strong model scores high and a weak one scores lower.
    """
    return f"ans-{_digest('reference', prompt)[:10]}"


def _difficulty(prompt: str) -> int:
    """Return a stable per-prompt difficulty in ``[0, 100)`` (version-independent)."""
    return int(_digest("difficulty", prompt)[:8], 16) % 100


def _makes_mistake(model_ref: str, prompt: str) -> bool:
    """Return True if this version answers ``prompt`` incorrectly (deterministic).

    A version gets a prompt wrong only when the prompt's difficulty is below the
    version's mistake-rate threshold. Because a newer version has a *lower*
    threshold, the set of prompts it answers correctly always contains the set a
    older version answers correctly — so a newer version never scores below an
    older one on the same suite (a clean, monotonic competence model).
    """
    return _difficulty(prompt) < _mistake_rate(model_ref)


def default_answer_fn(model_ref: str, prompt: str) -> str:
    """Deterministically simulate ``model_ref`` answering ``prompt``.

    When the (deterministic) version does not "make a mistake" it returns the
    :func:`reference_answer`; otherwise it returns a version-specific wrong
    answer. The result depends on both ``model_ref`` and ``prompt``, so
    different versions diverge on exactly the prompts they get wrong.
    """
    if _makes_mistake(model_ref, prompt):
        return f"wrong-{_digest(model_ref, prompt)[:10]}"
    return reference_answer(prompt)


# --------------------------------------------------------------------------- #
# FR-11: evaluate + compare
# --------------------------------------------------------------------------- #
def _score_item(answer: str, item: EvalItem) -> float:
    """Return ``1.0`` if ``answer`` matches ``item.expected`` else ``0.0``."""
    return 1.0 if _normalise(answer) == _normalise(item.expected) else 0.0


def evaluate(
    registry: ObjectStoreRegistry,
    model_ref: str,
    suite: list[EvalItem],
    suite_name: str = "default",
    answer_fn: Optional[AnswerFn] = None,
) -> EvalResult:
    """Evaluate ``model_ref`` against ``suite`` and return an :class:`EvalResult`.

    ``model_ref`` must exist in ``registry`` (else
    :class:`~gadziriro.core.errors.NotFound`). Each item is answered by
    ``answer_fn`` (defaults to the deterministic :func:`default_answer_fn`),
    scored by weighted normalised match, and aggregated to a ``0..1`` score.
    A few ``(prompt, answer)`` samples and full per-item detail are captured.
    """
    _resolve_model(registry, model_ref)  # existence check (FR-11 precondition)
    answerer = answer_fn or default_answer_fn

    per_item: list[dict[str, object]] = []
    samples: list[dict[str, str]] = []
    weighted_hits = 0.0
    total_weight = 0.0

    for item in suite:
        answer = answerer(model_ref, item.prompt)
        hit = _score_item(answer, item)
        weight = float(item.weight)
        weighted_hits += hit * weight
        total_weight += weight

        per_item.append(
            {
                "prompt": item.prompt,
                "expected": item.expected,
                "answer": answer,
                "correct": bool(hit),
                "weight": weight,
                "score": hit,
            }
        )
        if len(samples) < _SAMPLE_LIMIT:
            samples.append({"prompt": item.prompt, "answer": answer})

    score = (weighted_hits / total_weight) if total_weight else 0.0
    return EvalResult(
        model_ref=model_ref,
        suite=suite_name,
        score=score,
        per_item=tuple(per_item),
        samples=tuple(samples),
    )


def compare(
    registry: ObjectStoreRegistry,
    a_ref: str,
    b_ref: str,
    suite: list[EvalItem],
    answer_fn: Optional[AnswerFn] = None,
) -> ComparisonResult:
    """Evaluate ``a_ref`` and ``b_ref`` on the same ``suite`` side by side.

    Returns a :class:`ComparisonResult` with ``score_a``/``score_b``, their
    ``score_delta`` (``score_a - score_b``) and per-prompt ``sample_diffs``
    ``(prompt, answer_a, answer_b)``. ``weight_summary`` is left empty here; the
    weight-change view is :func:`gadziriro.evaluation.diff.model_diff` (FR-13).
    """
    result_a = evaluate(registry, a_ref, suite, answer_fn=answer_fn)
    result_b = evaluate(registry, b_ref, suite, answer_fn=answer_fn)

    answerer = answer_fn or default_answer_fn
    sample_diffs: list[dict[str, str]] = []
    for item in suite[:_SAMPLE_LIMIT]:
        sample_diffs.append(
            {
                "prompt": item.prompt,
                "answer_a": answerer(a_ref, item.prompt),
                "answer_b": answerer(b_ref, item.prompt),
            }
        )

    return ComparisonResult(
        a_ref=a_ref,
        b_ref=b_ref,
        score_a=result_a.score,
        score_b=result_b.score,
        score_delta=result_a.score - result_b.score,
        sample_diffs=tuple(sample_diffs),
    )
