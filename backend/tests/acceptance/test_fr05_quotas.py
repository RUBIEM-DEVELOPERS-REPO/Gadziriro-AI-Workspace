"""Acceptance test for FR-05: per-user quotas are enforced and recover.

Story: a user may hold only so many jobs at once. Extra submits past the cap are
denied while the user is full; once their running jobs finish through the runtime,
their quota recovers and new work is admitted again. Jobs run to completion via
the mock adapter.
"""

from __future__ import annotations

from gadziriro.core.errors import GadziriroError
from gadziriro.runtime.base import JobStatus
from gadziriro.runtime.mock import MockRuntimeAdapter
from gadziriro.scheduler import Quota, QuotaExceeded, Scheduler


def test_fr05_user_quota_enforced_and_recovers() -> None:
    adapter = MockRuntimeAdapter(gpu_count=2, gpu_memory_mb=24000)
    quota = Quota(max_concurrent_per_user=2, max_concurrent_per_project=100)
    sched = Scheduler(adapter, quota=quota)

    # Alice fills her two concurrent slots.
    sched.submit("alice", "research", ["python", "a.py"])
    sched.submit("alice", "research", ["python", "b.py"])
    assert sched.user_active_count("alice") == 2

    # A third submit while full is DENIED (QuotaExceeded is a GadziriroError).
    try:
        sched.submit("alice", "research", ["python", "c.py"])
        raised = False
    except QuotaExceeded as exc:
        raised = True
        assert isinstance(exc, GadziriroError)
    assert raised, "expected the over-cap submit to be denied"

    # Draining the queue runs every job to completion through the mock adapter.
    sched.drain()
    for job in sched.list_jobs():
        assert job.status is JobStatus.SUCCEEDED
    assert sched.user_active_count("alice") == 0

    # Quota recovered: Alice can submit again, and GPUs are back in the pool.
    recovered = sched.submit("alice", "research", ["python", "c.py"])
    assert recovered.status is JobStatus.PENDING
    sched.drain()
    assert sched.get_job(recovered.job_id).status is JobStatus.SUCCEEDED
    assert adapter.metrics().gpus_free == 2


def test_fr05_gpu_jobs_release_devices_on_completion() -> None:
    adapter = MockRuntimeAdapter(gpu_count=1, gpu_memory_mb=24000)
    sched = Scheduler(adapter, quota=Quota(max_concurrent_per_user=5))

    sched.submit("alice", "p", ["train"], gpu_memory_mb=24000)
    sched.submit("alice", "p", ["eval"], gpu_memory_mb=24000)
    # With only one device and jobs running one at a time (node cap), each job
    # takes the device at start and returns it on completion — so both succeed.
    sched.drain()
    assert all(j.status is JobStatus.SUCCEEDED for j in sched.list_jobs())
    assert adapter.metrics().gpus_free == 1
