"""In-memory runtime backend for tests and off-target development.

The mock simulates a small pool of virtual GPUs so the whole control plane
(session manager, gateway, CLI) can be exercised on any machine — no Docker, no
NVIDIA driver, no GPU. It is the default backend (see ``Settings.runtime_backend``)
and the only one touched by the test suite.

Privacy model (FR-20): a kernel started with ``allow_egress=False`` (the default)
is recorded with ``network_enabled=False``. Tests assert against the stored kernel
record to prove the no-network default is honored.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

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

# Sensible single-node defaults for a workstation with two 24 GB cards.
DEFAULT_GPU_COUNT = 2
DEFAULT_GPU_MEMORY_MB = 24000


@dataclass
class MockKernel:
    """A simulated running kernel, as tracked by :class:`MockRuntimeAdapter`.

    ``network_enabled`` mirrors ``allow_egress`` so tests can assert that the
    privacy-first default (no egress) seals the kernel off from the network.
    """

    kernel_id: str
    session_id: str
    image: str
    allow_egress: bool
    network_enabled: bool
    gpu: Optional[GpuAllocation]
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class MockJob:
    """A simulated job. The Phase 0 mock completes jobs synchronously."""

    job_id: str
    status: JobStatus
    gpu: Optional[GpuAllocation]


class MockRuntimeAdapter(RuntimeAdapter):
    """A fully in-memory :class:`RuntimeAdapter`.

    GPUs are modeled as a fixed pool of whole devices, each with ``gpu_memory_mb``
    of memory. ``allocate_gpu`` reserves a free device from the pool and raises
    :class:`RuntimeAdapterError` once the pool is exhausted; ``stop`` returns a
    kernel's (or job's) device to the pool. Pass ``gpu_count=0`` for a CPU-only
    host.
    """

    def __init__(
        self,
        gpu_count: int = DEFAULT_GPU_COUNT,
        gpu_memory_mb: int = DEFAULT_GPU_MEMORY_MB,
    ) -> None:
        if gpu_count < 0:
            raise ValueError("gpu_count must be >= 0")
        if gpu_count and gpu_memory_mb <= 0:
            raise ValueError("gpu_memory_mb must be > 0 when gpu_count > 0")
        self._gpu_count = gpu_count
        self._gpu_memory_mb = gpu_memory_mb
        # Indices of GPUs not currently reserved.
        self._free_gpus: set[int] = set(range(gpu_count))
        self._kernels: dict[str, MockKernel] = {}
        self._jobs: dict[str, MockJob] = {}

    # -- GPU pool --------------------------------------------------------

    def allocate_gpu(self, memory_mb: int, whole_device: bool = True) -> GpuAllocation:
        """Reserve a whole device from the pool (or a CPU-only grant).

        ``memory_mb <= 0`` is a CPU-only request and returns an allocation with
        no GPU ids. Otherwise a free device is reserved; when none remain a
        :class:`RuntimeAdapterError` is raised.
        """
        if memory_mb <= 0:
            return GpuAllocation(gpu_ids=(), memory_mb=0, whole_device=whole_device)
        if not self._free_gpus:
            raise RuntimeAdapterError(
                "no free GPUs: pool of " f"{self._gpu_count} device(s) is exhausted"
            )
        idx = min(self._free_gpus)
        self._free_gpus.remove(idx)
        granted = (
            self._gpu_memory_mb if whole_device else min(memory_mb, self._gpu_memory_mb)
        )
        return GpuAllocation(
            gpu_ids=(idx,), memory_mb=granted, whole_device=whole_device
        )

    def _release_gpu(self, gpu: Optional[GpuAllocation]) -> None:
        """Return any reserved devices in ``gpu`` to the free pool."""
        if gpu is None:
            return
        for idx in gpu.gpu_ids:
            self._free_gpus.add(idx)

    # -- kernels ---------------------------------------------------------

    def start_kernel(self, spec: KernelSpec) -> KernelHandle:
        """Record a simulated kernel and return a handle with a fresh id.

        The kernel's network state is ``spec.allow_egress`` — ``False`` (the
        default) seals it off with no network.
        """
        kernel_id = f"k-{uuid.uuid4().hex[:12]}"
        self._kernels[kernel_id] = MockKernel(
            kernel_id=kernel_id,
            session_id=spec.session_id,
            image=spec.image,
            allow_egress=spec.allow_egress,
            network_enabled=spec.allow_egress,
            gpu=spec.gpu,
            env=dict(spec.env),
        )
        return KernelHandle(
            session_id=spec.session_id,
            kernel_id=kernel_id,
            connection_file=None,
        )

    def kernel_record(self, kernel_id: str) -> MockKernel:
        """Return the stored kernel record (test/introspection helper)."""
        try:
            return self._kernels[kernel_id]
        except KeyError as exc:
            raise NotFound(f"unknown kernel: {kernel_id}") from exc

    def execute(self, kernel_id: str, code: str) -> dict[str, Any]:
        """Simulate executing one cell and return a trivial result (FR-01).

        If ``code`` is a simple arithmetic expression it is evaluated in a
        sandbox with no builtins; otherwise the source is echoed back. This is a
        stand-in for a real Jupyter execute reply — enough to prove a cell can be
        run through a session and produce output.
        """
        kernel = self.kernel_record(kernel_id)
        text = code.strip()
        try:
            value = eval(text, {"__builtins__": {}}, {})  # noqa: S307 - sandboxed mock
            output = repr(value)
            status = "ok"
        except Exception:  # noqa: BLE001 - any failure just echoes the source
            output = text
            status = "echo"
        return {
            "kernel_id": kernel.kernel_id,
            "status": status,
            "output": output,
        }

    # -- jobs ------------------------------------------------------------

    def run_job(self, spec: JobSpec) -> JobStatus:
        """Record a job as completed synchronously (the scheduler is Phase 1)."""
        self._jobs[spec.job_id] = MockJob(
            job_id=spec.job_id,
            status=JobStatus.SUCCEEDED,
            gpu=spec.gpu,
        )
        return JobStatus.SUCCEEDED

    # -- lifecycle -------------------------------------------------------

    def stop(self, handle_or_job_id: str) -> None:
        """Stop a kernel or job by id and release any GPU it held."""
        kernel = self._kernels.pop(handle_or_job_id, None)
        if kernel is not None:
            self._release_gpu(kernel.gpu)
            return
        job = self._jobs.pop(handle_or_job_id, None)
        if job is not None:
            self._release_gpu(job.gpu)
            return
        raise NotFound(f"unknown kernel or job: {handle_or_job_id}")

    # -- observability ---------------------------------------------------

    def metrics(self) -> RuntimeMetrics:
        """Return live counts for the simulated pool."""
        jobs_running = sum(
            1 for j in self._jobs.values() if j.status == JobStatus.RUNNING
        )
        return RuntimeMetrics(
            gpus_total=self._gpu_count,
            gpus_free=len(self._free_gpus),
            kernels_running=len(self._kernels),
            jobs_running=jobs_running,
        )
