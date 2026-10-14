"""Evaluation harness + model diff (FR-11, FR-13)."""

from .base import ComparisonResult, EvalItem, EvalResult
from .diff import model_diff
from .harness import compare, default_answer_fn, evaluate, reference_answer

__all__ = [
    "EvalItem",
    "EvalResult",
    "ComparisonResult",
    "evaluate",
    "compare",
    "default_answer_fn",
    "reference_answer",
    "model_diff",
]
