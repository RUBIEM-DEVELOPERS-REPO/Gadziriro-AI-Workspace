"""RuntimeAdapter contract. CRITICAL FILE — keep the 5-method surface stable.

This is the Phase 3 extension point (K8s / Slurm). Changing the method surface
breaks every backend and the control plane's assumptions, so additions should be
backward compatible.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(frozen=True)
class GpuAllocation:
    """A grant of GPU resource to a session or job."""

    gpu_ids: tuple[int, ...]  # physical/logical indices; empty tuple = CPU-only
    memory_mb: int  # total GPU memory granted
    whole_device: bool = True  # False when MIG-split or time-shared (Phase 3)

    @property
    def is_cpu_only(self) -> bool:
        return len(self.gpu_ids) == 0


@dataclass(frozen=True)
class KernelSpec:
    """Request to start a notebook kernel in a sealed session (FR-03)."""

    session_id: str
    image: str = "gadziriro/kernel:py311"
    gpu: Optional[GpuAllocation] = None
    # Privacy default: user code gets NO network (FR-20). The policy engine is the
    # only thing that may flip this, and only for an admin-approved path.
    allow_egress: bool = False
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KernelHandle:
    """Reference to a running kernel/container."""

    session_id: str
    kernel_id: str
    connection_file: Optional[str] = None  # Jupyter connection info (target backend)


@dataclass(frozen=True)
class JobSpec:
    """A long-running background job (e.g. a fine-tune); scheduler lands in Phase 1."""

    job_id: str
    command: list[str]
    gpu: Optional[GpuAllocation] = None
    allow_egress: bool = False
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeMetrics:
    """Point-in-time runtime stats surfaced to observability (FR-39)."""

    gpus_total: int
    gpus_free: int
    kernels_running: int
    jobs_running: int


class RuntimeAdapter(abc.ABC):
    """Five commands. That's the whole contract between control plane and hardware."""

    @abc.abstractmethod
    def start_kernel(self, spec: KernelSpec) -> KernelHandle:
        """Start a sealed kernel container and return a handle."""

    @abc.abstractmethod
    def run_job(self, spec: JobSpec) -> JobStatus:
        """Launch (or enqueue) a background job; returns its current status."""

    @abc.abstractmethod
    def allocate_gpu(self, memory_mb: int, whole_device: bool = True) -> GpuAllocation:
        """Reserve GPU resource; raises RuntimeAdapterError if none available."""

    @abc.abstractmethod
    def stop(self, handle_or_job_id: str) -> None:
        """Stop a kernel (by kernel_id) or job (by job_id) and release its GPU."""

    @abc.abstractmethod
    def metrics(self) -> RuntimeMetrics:
        """Return current runtime metrics."""
