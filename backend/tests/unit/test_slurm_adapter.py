"""Unit tests for the simulated Slurm runtime adapter."""

from __future__ import annotations

import pytest

from gadziriro.core.errors import NotFound, RuntimeAdapterError
from gadziriro.runtime.base import JobSpec, KernelSpec
from gadziriro.runtime.slurm import SlurmRuntimeAdapter


def test_submit_runner_is_used() -> None:
    calls: list[list[str]] = []

    def runner(cmd: list[str]) -> str:
        calls.append(cmd)
        return "slurm-xyz"

    s = SlurmRuntimeAdapter(total_gpus=2, submit_runner=runner)
    h = s.start_kernel(KernelSpec(session_id="s1"))
    assert h.kernel_id == "slurm-xyz"
    assert calls and calls[0][0] == "sbatch"


def test_pool_and_release() -> None:
    s = SlurmRuntimeAdapter(total_gpus=1, gpu_memory_mb=80000)
    gpu = s.allocate_gpu(80000)
    h = s.start_kernel(KernelSpec(session_id="s1", gpu=gpu))
    assert s.metrics().gpus_free == 0
    s.stop(h.kernel_id)
    assert s.metrics().gpus_free == 1


def test_exhaustion_and_jobs() -> None:
    s = SlurmRuntimeAdapter(total_gpus=1)
    s.allocate_gpu(80000)
    with pytest.raises(RuntimeAdapterError):
        s.allocate_gpu(80000)
    assert s.run_job(JobSpec(job_id="j1", command=["train"])).value == "running"
    assert s.complete_job("j1").value == "succeeded"
    with pytest.raises(NotFound):
        s.stop("nope")
