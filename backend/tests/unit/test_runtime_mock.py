"""Unit tests for the mock runtime adapter (the off-target GPU/kernel simulator)."""

from __future__ import annotations

import pytest

from gadziriro.core.errors import NotFound, RuntimeAdapterError
from gadziriro.runtime.base import JobSpec, KernelSpec
from gadziriro.runtime.mock import MockRuntimeAdapter


def test_allocate_until_exhausted_then_raises() -> None:
    adapter = MockRuntimeAdapter(gpu_count=2, gpu_memory_mb=24000)
    a = adapter.allocate_gpu(24000)
    b = adapter.allocate_gpu(24000)
    assert a.gpu_ids and b.gpu_ids and a.gpu_ids != b.gpu_ids
    with pytest.raises(RuntimeAdapterError):
        adapter.allocate_gpu(24000)


def test_cpu_only_allocation_is_not_from_pool() -> None:
    adapter = MockRuntimeAdapter(gpu_count=1)
    alloc = adapter.allocate_gpu(0)
    assert alloc.is_cpu_only
    # A CPU-only grant must not consume a device.
    assert adapter.metrics().gpus_free == 1


def test_stop_releases_gpu() -> None:
    adapter = MockRuntimeAdapter(gpu_count=1, gpu_memory_mb=24000)
    gpu = adapter.allocate_gpu(24000)
    handle = adapter.start_kernel(KernelSpec(session_id="s1", gpu=gpu))
    assert adapter.metrics().gpus_free == 0
    adapter.stop(handle.kernel_id)
    assert adapter.metrics().gpus_free == 1
    assert adapter.metrics().kernels_running == 0


def test_metrics_reflect_live_state() -> None:
    adapter = MockRuntimeAdapter(gpu_count=2, gpu_memory_mb=24000)
    adapter.start_kernel(KernelSpec(session_id="a"))
    adapter.start_kernel(KernelSpec(session_id="b"))
    m = adapter.metrics()
    assert m.gpus_total == 2
    assert m.kernels_running == 2


def test_default_kernel_has_no_network() -> None:
    # FR-20: the privacy default (allow_egress False) seals the kernel off.
    adapter = MockRuntimeAdapter(gpu_count=1)
    handle = adapter.start_kernel(KernelSpec(session_id="s1"))
    rec = adapter.kernel_record(handle.kernel_id)
    assert rec.allow_egress is False
    assert rec.network_enabled is False


def test_execute_returns_output() -> None:
    adapter = MockRuntimeAdapter(gpu_count=0)
    handle = adapter.start_kernel(KernelSpec(session_id="s1"))
    result = adapter.execute(handle.kernel_id, "1 + 1")
    assert result["output"] == "2"
    assert result["kernel_id"] == handle.kernel_id


def test_run_job_succeeds_synchronously() -> None:
    adapter = MockRuntimeAdapter(gpu_count=0)
    status = adapter.run_job(JobSpec(job_id="j1", command=["echo", "hi"]))
    assert status.value == "succeeded"


def test_stop_unknown_raises_not_found() -> None:
    adapter = MockRuntimeAdapter(gpu_count=0)
    with pytest.raises(NotFound):
        adapter.stop("does-not-exist")
