"""Evaluation contracts: question sets, scores, and version comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvalItem:
    """One test question and its expected answer / scoring key."""

    prompt: str
    expected: str
    weight: float = 1.0


@dataclass(frozen=True)
class EvalResult:
    model_ref: str
    suite: str
    score: float  # 0..1 aggregate
    per_item: tuple[dict[str, Any], ...] = ()
    samples: tuple[dict[str, str], ...] = ()  # (prompt, answer) samples


@dataclass(frozen=True)
class ComparisonResult:
    """Side-by-side comparison of two model versions (FR-11/FR-13)."""

    a_ref: str
    b_ref: str
    score_a: float
    score_b: float
    score_delta: float
    sample_diffs: tuple[dict[str, str], ...] = ()  # prompt, answer_a, answer_b
    weight_summary: dict[str, Any] = field(default_factory=dict)
