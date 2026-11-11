"""NFR-08 acceptance: the same control-plane calls work across backends.

Proves one software surface runs on 1 GPU (mock), Kubernetes, or Slurm with no
change to the calling code, policy, or screens — only the factory selection differs.
Real cluster verification is a target-hardware concern.
"""

from __future__ import annotations

import pytest

from gadziriro.core.config import Settings
from gadziriro.runtime.base import KernelSpec, RuntimeAdapter
from gadziriro.runtime.factory import get_runtime_adapter


def _exercise(adapter: RuntimeAdapter) -> None:
    # Identical five-method surface, whatever the backend.
    gpu = adapter.allocate_gpu(24000)
    handle = adapter.start_kernel(KernelSpec(session_id="s1", gpu=gpu))
    assert handle.kernel_id
    assert adapter.metrics().kernels_running == 1
    adapter.stop(handle.kernel_id)
    assert adapter.metrics().kernels_running == 0


@pytest.mark.parametrize("backend", ["mock", "kubernetes", "k8s", "slurm"])
def test_same_surface_across_backends(backend: str) -> None:
    import os

    os.environ["GADZIRIRO_RUNTIME_BACKEND"] = backend
    try:
        adapter = get_runtime_adapter(Settings())
        _exercise(adapter)
    finally:
        os.environ.pop("GADZIRIRO_RUNTIME_BACKEND", None)


@pytest.mark.target_hardware
def test_real_cluster_multinode() -> None:  # pragma: no cover - needs a cluster
    pytest.skip("Real K8s/Slurm cluster verified on the target deployment.")
