"""Evaluation routes (FR-11, FR-13) — run, compare, diff model versions.

Surfaces the deterministic evaluation harness over the injected registry:

* ``POST /api/evaluation/run`` — score one model version against a suite.
* ``POST /api/evaluation/compare`` — score two versions on the same suite.
* ``POST /api/evaluation/diff`` — compare two versions and summarise the
  (simulated) weight change; the suite is optional.

Every route requires an authenticated principal.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...auth.base import Principal
from ...evaluation.base import ComparisonResult, EvalItem, EvalResult
from ...evaluation.diff import model_diff
from ...evaluation.harness import compare, evaluate
from ...registry.store import ObjectStoreRegistry
from ..deps import get_current_principal, get_registry
from ..registry import register_router

router = APIRouter(tags=["evaluation"])


class SuiteItemIn(BaseModel):
    """One suite question (prompt, expected answer, optional weight)."""

    prompt: str
    expected: str
    weight: float = 1.0


class EvalRunIn(BaseModel):
    """Body for evaluating a single model version."""

    model_ref: str
    suite: list[SuiteItemIn]
    suite_name: str = "default"


class CompareIn(BaseModel):
    """Body for comparing two model versions on the same suite."""

    a_ref: str
    b_ref: str
    suite: list[SuiteItemIn]


class DiffIn(BaseModel):
    """Body for diffing two model versions (suite optional)."""

    a_ref: str
    b_ref: str
    suite: Optional[list[SuiteItemIn]] = None


def _to_items(suite: list[SuiteItemIn]) -> list[EvalItem]:
    """Convert wire suite items to :class:`EvalItem` instances."""
    return [
        EvalItem(prompt=i.prompt, expected=i.expected, weight=i.weight) for i in suite
    ]


def _result_to_dict(result: EvalResult) -> dict[str, Any]:
    """Project an :class:`EvalResult` onto a JSON-serialisable dict."""
    return {
        "model_ref": result.model_ref,
        "suite": result.suite,
        "score": result.score,
        "per_item": [dict(item) for item in result.per_item],
        "samples": [dict(sample) for sample in result.samples],
    }


def _comparison_to_dict(result: ComparisonResult) -> dict[str, Any]:
    """Project a :class:`ComparisonResult` onto a JSON-serialisable dict."""
    return {
        "a_ref": result.a_ref,
        "b_ref": result.b_ref,
        "score_a": result.score_a,
        "score_b": result.score_b,
        "score_delta": result.score_delta,
        "sample_diffs": [dict(diff) for diff in result.sample_diffs],
        "weight_summary": dict(result.weight_summary),
    }


@router.post("/run")
def run(
    body: EvalRunIn,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Evaluate ``model_ref`` against the supplied suite (FR-11).

    :raises NotFound: if the model does not exist (HTTP 404).
    """
    result = evaluate(
        registry, body.model_ref, _to_items(body.suite), suite_name=body.suite_name
    )
    return _result_to_dict(result)


@router.post("/compare")
def compare_models(
    body: CompareIn,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Compare two model versions on the same suite (FR-11).

    :raises NotFound: if either model does not exist (HTTP 404).
    """
    result = compare(registry, body.a_ref, body.b_ref, _to_items(body.suite))
    return _comparison_to_dict(result)


@router.post("/diff")
def diff(
    body: DiffIn,
    registry: Annotated[ObjectStoreRegistry, Depends(get_registry)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Diff two model versions, optionally scoring them on a suite (FR-13).

    :raises NotFound: if either model does not exist (HTTP 404).
    """
    suite = _to_items(body.suite) if body.suite is not None else None
    result = model_diff(registry, body.a_ref, body.b_ref, suite)
    return _comparison_to_dict(result)


register_router("/api/evaluation", router)
