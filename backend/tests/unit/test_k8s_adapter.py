"""Unit tests for the simulated Kubernetes runtime adapter."""

from __future__ import annotations

import pytest

from gadziriro.core.errors import NotFound, RuntimeAdapterError
from gadziriro.runtime.base import JobSpec, KernelSpec
from gadziriro.runtime.kubernetes import KubernetesRuntimeAdapter


def test_pool_exhaustion_raises() -> None:
    k = KubernetesRuntimeAdapter(nodes=1, gpus_per_node=2, gpu_memory_mb=80000)
    a = k.allocate_gpu(80000)
    b = k.allocate_gpu(80000)
    assert a.gpu_ids and b.gpu_ids and a.gpu_ids != b.gpu_ids
    with pytest.raises(RuntimeAdapterError):
        k.allocate_gpu(80000)


def test_start_stop_metrics() -> None:
    k = KubernetesRuntimeAdapter(nodes=2, gpus_per_node=2)
    gpu = k.allocate_gpu(80000)
    h = k.start_kernel(KernelSpec(session_id="s1", gpu=gpu))
    m = k.metrics()
    assert m.gpus_total == 4 and m.kernels_running == 1 and m.gpus_free == 3
    k.stop(h.kernel_id)
    assert k.metrics().gpus_free == 4 and k.metrics().kernels_running == 0


def test_default_pod_has_no_network() -> None:
    k = KubernetesRuntimeAdapter(nodes=1, gpus_per_node=1)
    h = k.start_kernel(KernelSpec(session_id="s1"))
    assert k.pod_record(h.kernel_id).network_enabled is False


def test_jobs_and_unknown_stop() -> None:
    k = KubernetesRuntimeAdapter(nodes=1, gpus_per_node=1)
    assert k.run_job(JobSpec(job_id="j1", command=["x"])).value == "running"
    assert k.complete_job("j1").value == "succeeded"
    with pytest.raises(NotFound):
        k.stop("nope")
