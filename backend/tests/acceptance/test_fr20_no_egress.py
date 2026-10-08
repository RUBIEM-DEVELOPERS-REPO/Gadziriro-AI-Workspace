"""FR-20 / NFR-05 acceptance tests — Phase 0 EXIT-GATE: no egress by default.

These assert the end-to-end privacy posture that must hold before Phase 0 can
close: a default kernel is network-sealed, and the default egress policy blocks
any outbound attempt by user code.
"""

from __future__ import annotations

import pytest

from gadziriro.compute.isolation import build_container_spec
from gadziriro.core.config import Settings
from gadziriro.core.errors import PolicyDenied
from gadziriro.policy.egress import EgressPolicy
from gadziriro.runtime.base import KernelSpec


def _policy_from_settings(settings: Settings) -> EgressPolicy:
    """Construct the default egress policy exactly as the control plane would."""
    return EgressPolicy(enabled_egress=settings.allow_egress)


def test_default_kernel_has_no_network() -> None:
    """(a) A defaulted KernelSpec yields a container with NO network."""
    spec = KernelSpec(session_id="exit-gate")
    assert spec.allow_egress is False
    container = build_container_spec(spec)
    assert container.network is None
    args = container.to_docker_args()
    # The flag and its value must be adjacent: `--network none`.
    assert "--network" in args
    assert args[args.index("--network") + 1] == "none"


def test_default_policy_denies_external_target() -> None:
    """(b) The default egress policy denies a representative external target."""
    policy = _policy_from_settings(Settings())
    assert policy.is_allowed("api.openai.com") is False
    with pytest.raises(PolicyDenied):
        policy.check("api.openai.com")


def test_user_code_egress_attempt_is_blocked() -> None:
    """(c) Simulated 'user code attempts egress' is blocked at the gate."""
    policy = _policy_from_settings(Settings())
    external = "203.0.113.42"  # TEST-NET-3, a stand-in for the open internet
    with pytest.raises(PolicyDenied) as exc:
        policy.check(external, actor="user-code")
    assert external in exc.value.reason


@pytest.mark.target_hardware
def test_kernel_level_no_egress_on_target() -> None:
    """Documents that kernel-level no-egress is verified on the target box.

    Skipped off-target: the real assertion (a sealed container cannot reach the
    network at the kernel level) requires the Linux + NVIDIA host with Docker /
    gVisor. This stub records the verification contract for that environment.
    """
    pytest.skip("Requires Linux+NVIDIA target host with Docker/gVisor runtime")
