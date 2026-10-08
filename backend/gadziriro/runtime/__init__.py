"""Runtime adapter: the ONLY path from the control plane to hardware.

The control plane never touches GPUs or containers directly — it calls the five
methods of `RuntimeAdapter` (start_kernel, run_job, allocate_gpu, stop, metrics).
The single-node backend ships first; Kubernetes and Slurm backends are added in
Phase 3 by implementing the same ABC, with NO change to screens or policy (NFR-08).
"""

from .base import (
    GpuAllocation,
    JobSpec,
    JobStatus,
    KernelHandle,
    KernelSpec,
    RuntimeAdapter,
    RuntimeMetrics,
)

__all__ = [
    "GpuAllocation",
    "JobSpec",
    "JobStatus",
    "KernelHandle",
    "KernelSpec",
    "RuntimeAdapter",
    "RuntimeMetrics",
]
