"""Scheduler contracts: jobs, quotas, and the scheduler surface (FR-05, NFR-07).

The scheduler sits between users and the runtime adapter. It owns *fairness* and
*finishing*: quotas keep one user or project from starving
the node, and a small node-level concurrency cap means running work is finished
before new work starts (NFR-07) — so one big fine-tune can own the box rather
than every job crawling at once.

A job occupies a *concurrency slot* from the moment it is submitted until it
finishes, i.e. while its status is PENDING or RUNNING. Quotas are counted against
those active slots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Union, runtime_checkable

from ..core.errors import GadziriroError
from ..runtime.base import JobSpec, JobStatus

# A submitted command is a token list (argv), but a bare string is accepted and
# normalised to a single-element argv by the scheduler.
Command = Union[list[str], str]

# Statuses that still occupy a concurrency slot (count against quotas).
ACTIVE_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.PENDING, JobStatus.RUNNING}
)


class QuotaExceeded(GadziriroError):
    """A submit was denied because a quota (user, project, or queue) is full."""


@dataclass
class Quota:
    """Fairness limits enforced at submit time.

    - ``max_concurrent_per_user``: active (PENDING+RUNNING) jobs one user may hold.
    - ``max_concurrent_per_project``: active jobs one project may hold.
    - ``max_queued``: total jobs allowed to wait in the PENDING queue.
    """

    max_concurrent_per_user: int = 2
    max_concurrent_per_project: int = 4
    max_queued: int = 32


@dataclass
class ScheduledJob:
    """One unit of scheduled work and its lifecycle timestamps."""

    job_id: str
    user: str
    project: str
    spec: JobSpec
    status: JobStatus = JobStatus.PENDING
    submitted_at: float = 0.0
    started_at: Optional[float] = None
    ended_at: Optional[float] = None

    @property
    def is_active(self) -> bool:
        """True while the job still holds a concurrency slot."""
        return self.status in ACTIVE_STATUSES


@runtime_checkable
class Scheduler(Protocol):
    """The scheduler surface the gateway/CLI depend on (not the implementation)."""

    def submit(
        self,
        user: str,
        project: str,
        command: Command,
        *,
        gpu_memory_mb: int = 0,
        allow_egress: bool = False,
    ) -> ScheduledJob:
        """Enqueue a job, or raise :class:`QuotaExceeded` if a quota is full."""
        ...

    def tick(self) -> Optional[ScheduledJob]:
        """Start the next queued job if node capacity allows; return it or None."""
        ...

    def list_jobs(self) -> list[ScheduledJob]:
        """Return every job the scheduler knows about."""
        ...

    def get_job(self, job_id: str) -> ScheduledJob:
        """Return one job by id, or raise :class:`~gadziriro.core.errors.NotFound`."""
        ...
