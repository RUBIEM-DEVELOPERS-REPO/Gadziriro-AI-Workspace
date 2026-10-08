"""Unit tests for idle GPU reclaim driven by an injected fake clock (FR-04)."""

from __future__ import annotations

from typing import Any

from gadziriro.audit.base import AuditEvent, VerifyResult
from gadziriro.runtime.mock import MockRuntimeAdapter
from gadziriro.scheduler import IdleReclaimer
from gadziriro.sessions.manager import SessionManager

TIMEOUT_S = 1800


class Clock:
    """A mutable fake clock; call it to read the current time."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> dict[str, Any]:
        self.events.append(event)
        return {"seq": len(self.events)}

    def verify(self) -> VerifyResult:
        return VerifyResult(ok=True, count=len(self.events))


def test_idle_session_reclaimed_fresh_kept() -> None:
    clock = Clock(1000.0)
    adapter = MockRuntimeAdapter(gpu_count=2, gpu_memory_mb=24000)
    mgr = SessionManager(adapter, now=clock)

    mgr.create_session("old", user="alice", gpu_memory_mb=24000)
    assert adapter.metrics().gpus_free == 1  # one device held by the idle session

    # Time moves past the idle window, then a fresh session is created.
    clock.t = 1000.0 + TIMEOUT_S + 1
    mgr.create_session("fresh", user="bob")

    reclaimer = IdleReclaimer(mgr, timeout_s=TIMEOUT_S, now=clock)
    reclaimed = reclaimer.reclaim()

    assert reclaimed == ["old"]
    assert adapter.metrics().gpus_free == 2  # GPU returned to the pool (FR-04)
    live = {s.session_id for s in mgr.list_sessions()}
    assert live == {"fresh"}


def test_run_cell_refreshes_activity() -> None:
    clock = Clock(0.0)
    mgr = SessionManager(MockRuntimeAdapter(gpu_count=1), now=clock)
    mgr.create_session("s1", user="alice")

    # Nearly idle, then activity bumps last_active.
    clock.t = TIMEOUT_S - 1
    mgr.run_cell("s1", "1 + 1")
    assert mgr.last_active("s1") == TIMEOUT_S - 1

    # Advance just past the timeout measured from the *new* last_active.
    clock.t = (TIMEOUT_S - 1) + 10
    reclaimer = IdleReclaimer(mgr, timeout_s=TIMEOUT_S, now=clock)
    assert reclaimer.reclaim() == []  # still within the window


def test_nothing_reclaimed_when_all_fresh() -> None:
    clock = Clock(500.0)
    mgr = SessionManager(MockRuntimeAdapter(gpu_count=2), now=clock)
    mgr.create_session("a", user="u1")
    mgr.create_session("b", user="u2")
    reclaimer = IdleReclaimer(mgr, timeout_s=TIMEOUT_S, now=clock)
    assert reclaimer.reclaim() == []
    assert len(mgr.list_sessions()) == 2


def test_reclaim_logs_to_audit() -> None:
    clock = Clock(0.0)
    audit = FakeAudit()
    mgr = SessionManager(MockRuntimeAdapter(gpu_count=1), audit=audit, now=clock)
    mgr.create_session("old", user="alice")

    clock.t = TIMEOUT_S + 100
    IdleReclaimer(mgr, timeout_s=TIMEOUT_S, now=clock).reclaim()

    actions = [e.action for e in audit.events]
    # stop_session emits session.stop; the reclaimer adds session.reclaim.
    assert "session.reclaim" in actions
    assert "session.stop" in actions
