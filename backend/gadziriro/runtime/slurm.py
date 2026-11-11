"""Slurm runtime backend (HPC multi-node, NFR-08).

Same five-method :class:`RuntimeAdapter` surface as every other backend. Jobs are
submitted through a Slurm controller (``sbatch``/``squeue``); the controller call is
injectable so the dev box (no Slurm) runs against a simulated partition. Importing
or constructing this adapter never requires Slurm to be installed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..core.errors import NotFound, RuntimeAdapterError
from .base import (
    GpuAllocation,
    JobSpec,
    JobStatus,
    KernelHandle,
    KernelSpec,
    RuntimeAdapter,
    RuntimeMetrics,
)

# A submit runner takes an sbatch-style command and returns a Slurm job id.
SubmitRunner = Callable[[list[str]], str]


def _simulated_sbatch(_command: list[str]) -> str:
    """Default runner: never shells out; returns a simulated Slurm job id."""
    return f"slurm-{uuid.uuid4().hex[:8]}"


@dataclass
class _Alloc:
    kernel_id: str
    session_id: str
    gpu: Optional[GpuAllocation]
    network_enabled: bool
    env: dict[str, str] = field(default_factory=dict)


class SlurmRuntimeAdapter(RuntimeAdapter):
    """A Slurm partition modelled as a flat pool of ``total_gpus`` whole GPUs."""

    def __init__(
        self,
        total_gpus: int = 8,
        gpu_memory_mb: int = 80000,
        *,
        partition: str = "gpu",
        submit_runner: Optional[SubmitRunner] = None,
    ) -> None:
        if total_gpus < 0:
            raise ValueError("total_gpus must be >= 0")
        self._total = total_gpus
        self._gpu_memory_mb = gpu_memory_mb
        self._partition = partition
        self._submit: SubmitRunner = submit_runner or _simulated_sbatch
        self._free: set[int] = set(range(total_gpus))
        self._allocs: dict[str, _Alloc] = {}
        self._jobs: dict[str, JobStatus] = {}

    # -- GPU pool --------------------------------------------------------

    def allocate_gpu(self, memory_mb: int, whole_device: bool = True) -> GpuAllocation:
        if memory_mb <= 0:
            return GpuAllocation(gpu_ids=(), memory_mb=0, whole_device=whole_device)
        if not self._free:
            raise RuntimeAdapterError(
                f"no free GPUs in partition {self._partition!r} ({self._total} total)"
            )
        idx = min(self._free)
        self._free.remove(idx)
        granted = (
            self._gpu_memory_mb if whole_device else min(memory_mb, self._gpu_memory_mb)
        )
        return GpuAllocation(
            gpu_ids=(idx,), memory_mb=granted, whole_device=whole_device
        )

    def _release(self, gpu: Optional[GpuAllocation]) -> None:
        if gpu is None:
            return
        for idx in gpu.gpu_ids:
            self._free.add(idx)

    # -- kernels ---------------------------------------------------------

    def start_kernel(self, spec: KernelSpec) -> KernelHandle:
        kernel_id = self._submit(["sbatch", "--partition", self._partition, spec.image])
        self._allocs[kernel_id] = _Alloc(
            kernel_id=kernel_id,
            session_id=spec.session_id,
            gpu=spec.gpu,
            network_enabled=spec.allow_egress,
            env=dict(spec.env),
        )
        return KernelHandle(
            session_id=spec.session_id, kernel_id=kernel_id, connection_file=None
        )

    def alloc_record(self, kernel_id: str) -> _Alloc:
        try:
            return self._allocs[kernel_id]
        except KeyError as exc:
            raise NotFound(f"unknown allocation: {kernel_id}") from exc

    # -- jobs ------------------------------------------------------------

    def run_job(self, spec: JobSpec) -> JobStatus:
        self._submit(["sbatch", "--partition", self._partition, *spec.command])
        self._jobs[spec.job_id] = JobStatus.RUNNING
        return JobStatus.RUNNING

    def complete_job(self, job_id: str) -> JobStatus:
        """Test/driver helper: mark a queued job finished."""
        if job_id not in self._jobs:
            raise NotFound(f"unknown job: {job_id}")
        self._jobs[job_id] = JobStatus.SUCCEEDED
        return JobStatus.SUCCEEDED

    # -- lifecycle -------------------------------------------------------

    def stop(self, handle_or_job_id: str) -> None:
        alloc = self._allocs.pop(handle_or_job_id, None)
        if alloc is not None:
            self._release(alloc.gpu)
            return
        if handle_or_job_id in self._jobs:
            del self._jobs[handle_or_job_id]
            return
        raise NotFound(f"unknown allocation or job: {handle_or_job_id}")

    # -- observability ---------------------------------------------------

    def metrics(self) -> RuntimeMetrics:
        jobs_running = sum(1 for s in self._jobs.values() if s == JobStatus.RUNNING)
        return RuntimeMetrics(
            gpus_total=self._total,
            gpus_free=len(self._free),
            kernels_running=len(self._allocs),
            jobs_running=jobs_running,
        )
