"""FIFO job scheduler with quotas and a finish-favouring run loop (FR-05, NFR-07).

The scheduler is deliberately small and single-node:

- ``submit`` enforces :class:`~gadziriro.scheduler.base.Quota` (per-user and
  per-project active slots, plus a bounded wait queue) and enqueues the job
  PENDING. A quota breach raises :class:`QuotaExceeded` — the submit is *denied*.
- ``tick``/``run_next`` starts the oldest queued job **only while the node has
  spare capacity** (``max_concurrent``). Keeping that cap small is the
  finish-favouring policy (NFR-07): the node drains running work before admitting
  more, so a single large job can effectively own the box instead of every job
  thrashing for the same GPUs.

The runtime is reached solely through the injected
:class:`~gadziriro.runtime.base.RuntimeAdapter`. A job that requests GPU memory is
allocated a device at start and has it released on completion, so slots recover.

Every submit / start / complete / deny is recorded to the optional
:class:`~gadziriro.audit.base.AuditSink`.
"""

from __future__ import annotations

import time
import uuid
from typing import Callable, Optional

from ..audit.base import AuditEvent, AuditSink
from ..core.errors import NotFound
from ..runtime.base import JobSpec, JobStatus, RuntimeAdapter
from .base import ACTIVE_STATUSES, Command, Quota, QuotaExceeded, ScheduledJob

# Finish-favouring default: one job owns the node at a time (NFR-07). Raise it
# only when the host can genuinely run several heavy jobs side by side.
DEFAULT_MAX_CONCURRENT = 1


class Scheduler:
    """A FIFO, quota-enforcing, finish-favouring job scheduler."""

    def __init__(
        self,
        adapter: RuntimeAdapter,
        *,
        quota: Quota,
        audit: Optional[AuditSink] = None,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        now: Callable[[], float] = time.time,
    ) -> None:
        """Wire the scheduler to a runtime adapter, a quota, and an optional sink.

        ``max_concurrent`` is the node-level cap on simultaneously RUNNING jobs
        (the finish-favouring knob, NFR-07). ``now`` is an injectable clock.
        """
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._adapter = adapter
        self._quota = quota
        self._audit = audit
        self._max_concurrent = max_concurrent
        self._now = now
        # Insertion order == submit order, so iterating gives FIFO for free.
        self._jobs: dict[str, ScheduledJob] = {}
        # Deferred GPU memory requests, keyed by job id, honoured at start time.
        self._gpu_requests: dict[str, int] = {}

    # -- submission (FR-05) ---------------------------------------------

    def submit(
        self,
        user: str,
        project: str,
        command: Command,
        *,
        gpu_memory_mb: int = 0,
        allow_egress: bool = False,
    ) -> ScheduledJob:
        """Enqueue a job for ``user``/``project`` or deny it on a quota breach.

        :raises QuotaExceeded: if the user or project is at its concurrent cap,
            or the wait queue is full.
        """
        if self.user_active_count(user) >= self._quota.max_concurrent_per_user:
            self._deny(user, project, "user concurrency cap reached")
        if self.project_active_count(project) >= self._quota.max_concurrent_per_project:
            self._deny(user, project, "project concurrency cap reached")
        if self.queued_count() >= self._quota.max_queued:
            self._deny(user, project, "queue is full")

        job_id = f"j-{uuid.uuid4().hex[:12]}"
        argv = [command] if isinstance(command, str) else list(command)
        spec = JobSpec(
            job_id=job_id,
            command=argv,
            gpu=None,  # GPU is reserved lazily at start time
            allow_egress=allow_egress,
            env={},
        )
        job = ScheduledJob(
            job_id=job_id,
            user=user,
            project=project,
            spec=spec,
            status=JobStatus.PENDING,
            submitted_at=self._now(),
        )
        # Carry the GPU request alongside the spec until the job starts.
        self._gpu_requests[job_id] = gpu_memory_mb
        self._jobs[job_id] = job
        self._log("job.submit", user, job_id, {"project": project, "command": argv})
        return job

    # -- run loop (NFR-07) ----------------------------------------------

    def tick(self) -> Optional[ScheduledJob]:
        """Start the oldest queued job if the node has capacity; else do nothing.

        Returns the job that was started (and, with the synchronous mock backend,
        completed) this tick, or ``None`` when there is nothing runnable or the
        node is at ``max_concurrent``.
        """
        if self.running_count() >= self._max_concurrent:
            return None
        job = self._next_pending()
        if job is None:
            return None
        self._start(job)
        return job

    # ``run_next`` is a readability alias for ``tick``.
    run_next = tick

    def drain(self, max_ticks: int = 10_000) -> int:
        """Run ticks until the queue is empty (or ``max_ticks``); return # started.

        A convenience for the synchronous mock backend and acceptance tests.
        """
        started = 0
        for _ in range(max_ticks):
            if self.tick() is None:
                break
            started += 1
        return started

    # -- queries / counts (for quota checks) ----------------------------

    def list_jobs(self) -> list[ScheduledJob]:
        """Return every known job in submit order."""
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> ScheduledJob:
        """Return one job, or raise :class:`NotFound`."""
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise NotFound(f"unknown job: {job_id}") from exc

    def user_active_count(self, user: str) -> int:
        """Active (PENDING+RUNNING) jobs held by ``user``."""
        return sum(
            1
            for j in self._jobs.values()
            if j.user == user and j.status in ACTIVE_STATUSES
        )

    def project_active_count(self, project: str) -> int:
        """Active (PENDING+RUNNING) jobs held by ``project``."""
        return sum(
            1
            for j in self._jobs.values()
            if j.project == project and j.status in ACTIVE_STATUSES
        )

    def queued_count(self) -> int:
        """Jobs currently waiting in the PENDING queue."""
        return sum(1 for j in self._jobs.values() if j.status == JobStatus.PENDING)

    def running_count(self) -> int:
        """Jobs currently RUNNING on the node."""
        return sum(1 for j in self._jobs.values() if j.status == JobStatus.RUNNING)

    # -- internals -------------------------------------------------------

    def _next_pending(self) -> Optional[ScheduledJob]:
        for job in self._jobs.values():  # dict preserves submit (FIFO) order
            if job.status == JobStatus.PENDING:
                return job
        return None

    def _start(self, job: ScheduledJob) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = self._now()
        self._log("job.start", job.user, job.job_id, {"project": job.project})

        gpu_memory_mb = self._gpu_requests.get(job.job_id, 0)
        gpu = None
        if gpu_memory_mb > 0:
            gpu = self._adapter.allocate_gpu(gpu_memory_mb)
        spec = JobSpec(
            job_id=job.spec.job_id,
            command=list(job.spec.command),
            gpu=gpu,
            allow_egress=job.spec.allow_egress,
            env=dict(job.spec.env),
        )
        job.spec = spec

        status = self._adapter.run_job(spec)
        self._complete(job, status)

    def _complete(self, job: ScheduledJob, status: JobStatus) -> None:
        job.status = status
        job.ended_at = self._now()
        # Release the device the job held back to the pool so the slot recovers.
        try:
            self._adapter.stop(job.job_id)
        except NotFound:
            # Backend did not retain a handle for this job; nothing to release.
            pass
        self._log(
            "job.complete",
            job.user,
            job.job_id,
            {"project": job.project, "status": status.value},
        )

    def _deny(self, user: str, project: str, reason: str) -> None:
        self._log(
            "job.deny",
            user,
            project,
            {"reason": reason},
            level="warn",
        )
        raise QuotaExceeded(reason)

    def _log(
        self,
        action: str,
        actor: str,
        target: str,
        meta: dict,
        *,
        level: str = "info",
    ) -> None:
        if self._audit is None:
            return
        self._audit.append(
            AuditEvent(
                actor=actor,
                action=action,
                target=target,
                level=level,
                meta=meta,
            )
        )
