"""Single-node Docker runtime backend (TARGET-ONLY).

Runs sealed, rootless kernel containers on a real Docker engine with the NVIDIA
runtime. Never exercised by the test suite: there is no Docker engine or GPU on
the dev host, so ``import docker`` is kept lazy (inside methods) and every SDK
call is funneled through small wrappers, so importing this module never fails
off-target.

The hardening flags here mirror ``gadziriro.compute.isolation.ContainerSpec``
(the CLI-oriented spec); this backend renders them as docker-py ``run()`` kwargs
instead. Either way the network is disabled unless ``allow_egress`` is set (FR-20).
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from ..core.config import Settings, load_settings
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


def _build_run_kwargs(kernel_spec: KernelSpec) -> dict[str, Any]:
    """Build docker-py ``containers.run`` kwargs for a sealed kernel container.

    Privacy default (FR-20): with ``allow_egress`` False the container gets no
    network at all. Rootless / no-new-privileges / read-only root / cap-drop ALL
    mirror the isolation spec in ``gadziriro.compute.isolation``.
    """
    gpu_ids = list(kernel_spec.gpu.gpu_ids) if kernel_spec.gpu else []
    config: dict[str, Any] = {
        "image": kernel_spec.image,
        "detach": True,
        "environment": dict(kernel_spec.env),
        # Rootless / hardened defaults.
        "security_opt": ["no-new-privileges"],
        "cap_drop": ["ALL"],
        "read_only": True,
        # Privacy default: NO network unless egress was explicitly opened.
        "network_disabled": not kernel_spec.allow_egress,
        "network_mode": "bridge" if kernel_spec.allow_egress else "none",
    }
    if gpu_ids:
        # NVIDIA device request for the reserved GPU indices.
        config["device_requests"] = [
            {
                "Driver": "nvidia",
                "DeviceIDs": [str(i) for i in gpu_ids],
                "Capabilities": [["gpu"]],
            }
        ]
    return config


class DockerRuntimeAdapter(RuntimeAdapter):
    """Real single-node backend over the Docker Engine API.

    All SDK access is lazy and wrapped so that merely importing or constructing
    this class never requires a running engine. Methods that must talk to Docker
    connect on first use via :meth:`_client`.
    """

    def __init__(
        self,
        gpu_count: int = 0,
        gpu_memory_mb: int = 0,
        *,
        settings: Optional[Settings] = None,
    ) -> None:
        self._settings = settings or load_settings()
        self._gpu_count = gpu_count
        self._gpu_memory_mb = gpu_memory_mb
        self._free_gpus: set[int] = set(range(gpu_count))
        # kernel_id/job_id -> {"container_id": str, "gpu": GpuAllocation|None}
        self._containers: dict[str, dict[str, Any]] = {}
        self._client_obj: Any = None

    # -- lazy client -----------------------------------------------------

    def _client(self) -> Any:
        """Connect to the local Docker engine, importing the SDK lazily."""
        if self._client_obj is None:
            try:
                import docker  # local import keeps module import safe off-target
            except ImportError as exc:  # pragma: no cover - target-only path
                raise RuntimeAdapterError(
                    "the 'docker' package is required for the docker backend"
                ) from exc
            try:
                self._client_obj = docker.from_env()
            except Exception as exc:  # pragma: no cover - target-only path
                raise RuntimeAdapterError(
                    f"cannot reach the Docker engine: {exc}"
                ) from exc
        return self._client_obj

    # -- GPU pool --------------------------------------------------------

    def allocate_gpu(self, memory_mb: int, whole_device: bool = True) -> GpuAllocation:
        """Reserve a whole GPU from the configured pool (CPU-only if 0 MB)."""
        if memory_mb <= 0:
            return GpuAllocation(gpu_ids=(), memory_mb=0, whole_device=whole_device)
        if not self._free_gpus:
            raise RuntimeAdapterError("no free GPUs on this node")
        idx = min(self._free_gpus)
        self._free_gpus.remove(idx)
        granted = (
            self._gpu_memory_mb if whole_device else min(memory_mb, self._gpu_memory_mb)
        )
        return GpuAllocation(
            gpu_ids=(idx,), memory_mb=granted, whole_device=whole_device
        )

    def _release_gpu(self, gpu: Optional[GpuAllocation]) -> None:
        if gpu is None:
            return
        for idx in gpu.gpu_ids:
            self._free_gpus.add(idx)

    # -- kernels ---------------------------------------------------------

    def start_kernel(self, spec: KernelSpec) -> KernelHandle:  # pragma: no cover
        """Start a sealed kernel container (requires a real engine)."""
        config = _build_run_kwargs(spec)
        client = self._client()
        container = client.containers.run(**config)
        kernel_id = f"k-{uuid.uuid4().hex[:12]}"
        self._containers[kernel_id] = {
            "container_id": container.id,
            "gpu": spec.gpu,
        }
        return KernelHandle(
            session_id=spec.session_id,
            kernel_id=kernel_id,
            connection_file=None,
        )

    # -- jobs ------------------------------------------------------------

    def run_job(self, spec: JobSpec) -> JobStatus:  # pragma: no cover
        """Launch a background job container (requires a real engine)."""
        client = self._client()
        container = client.containers.run(
            image="gadziriro/kernel:py311",
            command=spec.command,
            detach=True,
            environment=dict(spec.env),
            network_disabled=not spec.allow_egress,
        )
        self._containers[spec.job_id] = {
            "container_id": container.id,
            "gpu": spec.gpu,
        }
        return JobStatus.RUNNING

    # -- lifecycle -------------------------------------------------------

    def stop(self, handle_or_job_id: str) -> None:  # pragma: no cover
        """Stop and remove a container, releasing its GPU."""
        record = self._containers.pop(handle_or_job_id, None)
        if record is None:
            raise NotFound(f"unknown kernel or job: {handle_or_job_id}")
        client = self._client()
        try:
            container = client.containers.get(record["container_id"])
            container.remove(force=True)
        except Exception as exc:
            raise RuntimeAdapterError(f"failed to stop container: {exc}") from exc
        finally:
            self._release_gpu(record["gpu"])

    # -- observability ---------------------------------------------------

    def metrics(self) -> RuntimeMetrics:  # pragma: no cover
        """Return live runtime metrics for this node."""
        return RuntimeMetrics(
            gpus_total=self._gpu_count,
            gpus_free=len(self._free_gpus),
            kernels_running=len(self._containers),
            jobs_running=0,
        )
