"""Kubernetes runtime backend (multi-node, NFR-08).

Implements the same five-method :class:`RuntimeAdapter` surface as the single-node
backends, so screens and the policy layer do not change when a customer scales from
one box to a cluster. The real ``kubernetes`` client is imported lazily and only
when a live cluster is used; on the dev box (no cluster, package absent) the adapter
runs against an in-memory simulated cluster so the whole control plane is testable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

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


@dataclass
class _Pod:
    kernel_id: str
    session_id: str
    node: int
    gpu: Optional[GpuAllocation]
    network_enabled: bool
    env: dict[str, str] = field(default_factory=dict)


class KubernetesRuntimeAdapter(RuntimeAdapter):
    """A cluster modelled as ``nodes`` x ``gpus_per_node`` whole GPUs.

    GPU ids are global indices ``node * gpus_per_node + slot``. A real client is
    reached through :meth:`_client` (lazy ``import kubernetes``); every method here
    works against the in-memory pool so unit tests never need a cluster.
    """

    def __init__(
        self,
        nodes: int = 2,
        gpus_per_node: int = 4,
        gpu_memory_mb: int = 80000,
        *,
        namespace: str = "gadziriro",
    ) -> None:
        if nodes < 0 or gpus_per_node < 0:
            raise ValueError("nodes and gpus_per_node must be >= 0")
        self._nodes = nodes
        self._gpus_per_node = gpus_per_node
        self._gpu_memory_mb = gpu_memory_mb
        self._namespace = namespace
        self._free: set[int] = set(range(nodes * gpus_per_node))
        self._pods: dict[str, _Pod] = {}
        self._jobs: dict[str, JobStatus] = {}
        self._client_obj = None

    # -- real client (target-only) --------------------------------------

    def _client(self):  # pragma: no cover - target-only path
        """Lazily connect to the cluster; raises if the SDK is unavailable."""
        if self._client_obj is None:
            try:
                from kubernetes import client, config
            except ImportError as exc:
                raise RuntimeAdapterError(
                    "the 'kubernetes' package is required for a live cluster"
                ) from exc
            config.load_incluster_config()
            self._client_obj = client.CoreV1Api()
        return self._client_obj

    # -- GPU pool --------------------------------------------------------

    def allocate_gpu(self, memory_mb: int, whole_device: bool = True) -> GpuAllocation:
        if memory_mb <= 0:
            return GpuAllocation(gpu_ids=(), memory_mb=0, whole_device=whole_device)
        if not self._free:
            total = self._nodes * self._gpus_per_node
            raise RuntimeAdapterError(f"cluster GPU pool exhausted ({total} total)")
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

    def _node_of(self, gpu: Optional[GpuAllocation]) -> int:
        if gpu is None or not gpu.gpu_ids:
            return 0
        return gpu.gpu_ids[0] // max(self._gpus_per_node, 1)

    # -- kernels ---------------------------------------------------------

    def start_kernel(self, spec: KernelSpec) -> KernelHandle:
        kernel_id = f"pod-{uuid.uuid4().hex[:12]}"
        self._pods[kernel_id] = _Pod(
            kernel_id=kernel_id,
            session_id=spec.session_id,
            node=self._node_of(spec.gpu),
            gpu=spec.gpu,
            network_enabled=spec.allow_egress,
            env=dict(spec.env),
        )
        return KernelHandle(
            session_id=spec.session_id, kernel_id=kernel_id, connection_file=None
        )

    def pod_record(self, kernel_id: str) -> _Pod:
        try:
            return self._pods[kernel_id]
        except KeyError as exc:
            raise NotFound(f"unknown pod: {kernel_id}") from exc

    # -- jobs ------------------------------------------------------------

    def run_job(self, spec: JobSpec) -> JobStatus:
        # A cluster Job runs asynchronously; the simulated cluster marks it running.
        self._jobs[spec.job_id] = JobStatus.RUNNING
        return JobStatus.RUNNING

    def complete_job(self, job_id: str) -> JobStatus:
        """Test/driver helper: mark a running job finished."""
        if job_id not in self._jobs:
            raise NotFound(f"unknown job: {job_id}")
        self._jobs[job_id] = JobStatus.SUCCEEDED
        return JobStatus.SUCCEEDED

    # -- lifecycle -------------------------------------------------------

    def stop(self, handle_or_job_id: str) -> None:
        pod = self._pods.pop(handle_or_job_id, None)
        if pod is not None:
            self._release(pod.gpu)
            return
        if handle_or_job_id in self._jobs:
            del self._jobs[handle_or_job_id]
            return
        raise NotFound(f"unknown pod or job: {handle_or_job_id}")

    # -- observability ---------------------------------------------------

    def metrics(self) -> RuntimeMetrics:
        total = self._nodes * self._gpus_per_node
        jobs_running = sum(1 for s in self._jobs.values() if s == JobStatus.RUNNING)
        return RuntimeMetrics(
            gpus_total=total,
            gpus_free=len(self._free),
            kernels_running=len(self._pods),
            jobs_running=jobs_running,
        )
