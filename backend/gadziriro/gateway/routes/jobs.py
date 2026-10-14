"""Job routes (FR-05) — quota-enforced submission over the scheduler.

``POST /api/jobs`` submits a command for the caller's username to the injected
:class:`~gadziriro.scheduler.queue.Scheduler`; the scheduler enforces per-user /
per-project / queue quotas and raises
:class:`~gadziriro.scheduler.base.QuotaExceeded` (mapped to HTTP 429) on a
breach. After submission the queue is drained so the (synchronous mock) backend
runs the work. ``GET /api/jobs`` lists jobs and ``GET /api/jobs/{id}`` returns
one. Every route requires an authenticated principal.
"""

from __future__ import annotations

from typing import Annotated, Any, Union

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...auth.base import Principal
from ...scheduler.base import ScheduledJob
from ...scheduler.queue import Scheduler
from ..deps import get_current_principal, get_scheduler
from ..registry import register_router

router = APIRouter(tags=["jobs"])


class SubmitJobIn(BaseModel):
    """Body for submitting a job."""

    command: Union[str, list[str]]
    project: str = Field(default="default")
    gpu_memory_mb: int = 0
    allow_egress: bool = False


def _job_to_dict(job: ScheduledJob) -> dict[str, Any]:
    """Project a :class:`ScheduledJob` onto a JSON-serialisable dict."""
    return {
        "job_id": job.job_id,
        "user": job.user,
        "project": job.project,
        "command": list(job.spec.command),
        "status": job.status.value,
        "submitted_at": job.submitted_at,
        "started_at": job.started_at,
        "ended_at": job.ended_at,
    }


@router.get("")
def list_jobs(
    scheduler: Annotated[Scheduler, Depends(get_scheduler)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> list[dict[str, Any]]:
    """List every job the scheduler knows about (submit order)."""
    return [_job_to_dict(job) for job in scheduler.list_jobs()]


@router.post("")
def submit_job(
    body: SubmitJobIn,
    scheduler: Annotated[Scheduler, Depends(get_scheduler)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Submit a job for the caller and run the queue.

    :raises QuotaExceeded: if a user/project/queue quota is full
        (mapped to HTTP 429).
    """
    job = scheduler.submit(
        principal.username,
        body.project,
        body.command,
        gpu_memory_mb=body.gpu_memory_mb,
        allow_egress=body.allow_egress,
    )
    scheduler.drain()
    return _job_to_dict(scheduler.get_job(job.job_id))


@router.get("/{job_id}")
def get_job(
    job_id: str,
    scheduler: Annotated[Scheduler, Depends(get_scheduler)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Return one job by id.

    :raises NotFound: if the job does not exist (mapped to HTTP 404).
    """
    return _job_to_dict(scheduler.get_job(job_id))


register_router("/api/jobs", router)
