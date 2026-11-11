"""Unit tests for red-team testing."""

from __future__ import annotations

from gadziriro.redteam.redteam import UNSAFE_MARKER, run_red_team


def test_safe_model_passes() -> None:
    r = run_red_team("m@1")  # default safe-refusing answer_fn
    assert r.passed is True
    assert r.total == 3
    assert r.unsafe == ()


def test_unsafe_model_flagged() -> None:
    def compromised(model_ref, prompt):
        return f"{UNSAFE_MARKER}: here you go"

    r = run_red_team("m@1", answer_fn=compromised)
    assert r.passed is False
    assert len(r.unsafe) == 3
    assert {u["category"] for u in r.unsafe} == {"jailbreak", "pii_exfil", "harmful"}


def test_custom_predicate() -> None:
    r = run_red_team(
        "m@1",
        answer_fn=lambda mr, p: "LEAK",
        is_unsafe=lambda a: a == "LEAK",
    )
    assert r.passed is False
