"""Unit tests for the job scheduler: quotas, FIFO, slot recovery, audit (FR-05)."""

from __future__ import annotations

from typing import Any

import pytest

from gadziriro.audit.base import AuditEvent, VerifyResult
from gadziriro.core.errors import NotFound
from gadziriro.runtime.base import JobStatus
from gadziriro.runtime.mock import MockRuntimeAdapter
from gadziriro.scheduler import Quota, QuotaExceeded, Scheduler


class FakeAudit:
    """A minimal AuditSink that records appended events."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> dict[str, Any]:
        self.events.append(event)
        return {"seq": len(self.events), "action": event.action}

    def verify(self) -> VerifyResult:
        return VerifyResult(ok=True, count=len(self.events))


def _sched(**quota: int) -> Scheduler:
    q = Quota(**quota) if quota else Quota()
    return Scheduler(MockRuntimeAdapter(gpu_count=2), quota=q)


def test_submit_enqueues_pending() -> None:
    sched = _sched()
    job = sched.submit("alice", "proj", ["python", "train.py"])
    assert job.status is JobStatus.PENDING
    assert job.user == "alice"
    assert job.project == "proj"
    assert sched.queued_count() == 1
    assert sched.get_job(job.job_id) is job


def test_user_concurrency_cap_denies() -> None:
    sched = _sched(max_concurrent_per_user=2, max_concurrent_per_project=100)
    sched.submit("alice", "p", ["a"])
    sched.submit("alice", "p", ["b"])
    with pytest.raises(QuotaExceeded):
        sched.submit("alice", "p", ["c"])
    # A different user is unaffected.
    assert sched.submit("bob", "p", ["d"]).status is JobStatus.PENDING


def test_project_concurrency_cap_denies() -> None:
    sched = _sched(max_concurrent_per_user=100, max_concurrent_per_project=2)
    sched.submit("alice", "shared", ["a"])
    sched.submit("bob", "shared", ["b"])
    with pytest.raises(QuotaExceeded):
        sched.submit("carol", "shared", ["c"])


def test_full_queue_denies() -> None:
    sched = _sched(
        max_concurrent_per_user=100, max_concurrent_per_project=100, max_queued=1
    )
    sched.submit("alice", "p", ["a"])
    with pytest.raises(QuotaExceeded):
        sched.submit("bob", "q", ["b"])


def test_fifo_order() -> None:
    sched = _sched(max_concurrent_per_user=100, max_concurrent_per_project=100)
    j1 = sched.submit("alice", "p", ["a"])
    j2 = sched.submit("alice", "p", ["b"])
    j3 = sched.submit("alice", "p", ["c"])
    started = [sched.tick().job_id for _ in range(3)]
    assert started == [j1.job_id, j2.job_id, j3.job_id]
    assert sched.tick() is None  # nothing left to run


def test_completion_frees_a_slot() -> None:
    sched = _sched(max_concurrent_per_user=1, max_concurrent_per_project=100)
    j1 = sched.submit("alice", "p", ["a"])
    with pytest.raises(QuotaExceeded):
        sched.submit("alice", "p", ["b"])  # at the per-user cap

    ran = sched.tick()
    assert ran.job_id == j1.job_id
    assert ran.status is JobStatus.SUCCEEDED
    assert sched.user_active_count("alice") == 0

    # The freed slot lets the next job in.
    j2 = sched.submit("alice", "p", ["b"])
    assert j2.status is JobStatus.PENDING


def test_tick_respects_node_concurrency_cap() -> None:
    # A stub adapter that leaves jobs RUNNING so the node cap is observable.
    class StuckAdapter(MockRuntimeAdapter):
        def run_job(self, spec):  # type: ignore[override]
            return JobStatus.RUNNING

    sched = Scheduler(
        StuckAdapter(gpu_count=2),
        quota=Quota(max_concurrent_per_user=100, max_concurrent_per_project=100),
        max_concurrent=1,
    )
    sched.submit("alice", "p", ["a"])
    sched.submit("alice", "p", ["b"])
    first = sched.tick()
    assert first is not None and first.status is JobStatus.RUNNING
    # One job already running and the node cap is 1, so the next tick is a no-op.
    assert sched.tick() is None
    assert sched.running_count() == 1


def test_get_unknown_job_raises() -> None:
    sched = _sched()
    with pytest.raises(NotFound):
        sched.get_job("nope")


def test_audit_events_emitted() -> None:
    audit = FakeAudit()
    sched = Scheduler(
        MockRuntimeAdapter(gpu_count=1),
        quota=Quota(max_concurrent_per_user=1, max_concurrent_per_project=100),
        audit=audit,
    )
    sched.submit("alice", "p", ["a"])
    with pytest.raises(QuotaExceeded):
        sched.submit("alice", "p", ["b"])
    sched.tick()
    actions = [e.action for e in audit.events]
    assert actions == ["job.submit", "job.deny", "job.start", "job.complete"]


def test_no_audit_when_sink_absent() -> None:
    sched = _sched()
    sched.submit("alice", "p", ["a"])  # must not raise
    sched.tick()
