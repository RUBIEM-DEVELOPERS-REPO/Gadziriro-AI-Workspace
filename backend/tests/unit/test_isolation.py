"""Unit tests for the container isolation spec builder (FR-20, NFR-05)."""

from __future__ import annotations

from gadziriro.compute.isolation import ContainerSpec, build_container_spec
from gadziriro.runtime.base import GpuAllocation, KernelSpec


def _args_pairs(args: list[str]) -> set[tuple[str, str]]:
    """Collect (flag, value) pairs for flags that take a following value."""
    pairs: set[tuple[str, str]] = set()
    for i, tok in enumerate(args[:-1]):
        if tok.startswith("--"):
            pairs.add((tok, args[i + 1]))
    return pairs


def test_default_no_egress_is_sealed() -> None:
    spec = build_container_spec(KernelSpec(session_id="s1"))
    assert spec.network is None
    args = spec.to_docker_args()
    pairs = _args_pairs(args)
    assert ("--network", "none") in pairs
    assert "--read-only" in args
    assert ("--cap-drop", "ALL") in pairs


def test_gvisor_runtime_rendered() -> None:
    spec = build_container_spec(KernelSpec(session_id="s1"), gvisor=True)
    assert spec.runtime == "runsc"
    assert ("--runtime", "runsc") in _args_pairs(spec.to_docker_args())


def test_no_gvisor_omits_runtime() -> None:
    spec = build_container_spec(KernelSpec(session_id="s1"), gvisor=False)
    assert spec.runtime is None
    assert "--runtime" not in spec.to_docker_args()


def test_gpu_allocation_renders_gpus_flag() -> None:
    gpu = GpuAllocation(gpu_ids=(0, 1), memory_mb=8000)
    spec = build_container_spec(KernelSpec(session_id="s1", gpu=gpu))
    assert spec.gpu_ids == (0, 1)
    assert "--gpus" in spec.to_docker_args()


def test_cpu_only_omits_gpus_flag() -> None:
    spec = build_container_spec(KernelSpec(session_id="s1"))
    assert spec.gpu_ids == ()
    assert "--gpus" not in spec.to_docker_args()


def test_allow_egress_permits_bridge_network() -> None:
    spec = build_container_spec(KernelSpec(session_id="s1", allow_egress=True))
    assert spec.network == "bridge"
    assert ("--network", "bridge") in _args_pairs(spec.to_docker_args())


def test_container_spec_is_frozen() -> None:
    spec = ContainerSpec(image="img")
    try:
        spec.image = "other"  # type: ignore[misc]
    except Exception as exc:  # FrozenInstanceError
        assert "cannot assign" in str(exc).lower() or True
    else:  # pragma: no cover
        raise AssertionError("ContainerSpec should be frozen")


def test_hardening_defaults() -> None:
    spec = build_container_spec(KernelSpec(session_id="s1"))
    assert spec.rootless is True
    assert spec.read_only_root is True
    assert spec.cap_drop == ("ALL",)
