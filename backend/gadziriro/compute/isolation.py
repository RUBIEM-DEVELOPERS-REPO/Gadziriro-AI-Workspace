"""Container isolation spec builder (FR-20, NFR-05).

Translates a :class:`~gadziriro.runtime.base.KernelSpec` into a concrete,
sealed container specification. The Docker runtime backend consumes
:class:`ContainerSpec` to launch rootless, read-only, capability-dropped
containers that — by privacy default — have NO network at all.

The single most important invariant: unless egress was explicitly approved
(``kernel_spec.allow_egress is True``), the rendered container gets
``--network none``. Everything else (gVisor, rootless, read-only root,
dropping all capabilities) hardens the sandbox further.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from gadziriro.runtime.base import KernelSpec


@dataclass(frozen=True)
class ContainerSpec:
    """A fully-resolved, immutable description of a sealed container.

    Attributes:
        image: Container image reference.
        network: Docker network to join. ``None`` means NO network at all,
            which renders as ``--network none`` (the privacy default).
        runtime: Container runtime, e.g. ``"runsc"`` for gVisor on the target
            host, or ``None`` to use the host default runtime.
        rootless: Informational flag; the container is expected to run under a
            rootless daemon / userns-remapped engine. Not a CLI flag itself.
        gpu_ids: Physical/logical GPU indices to expose. Empty means CPU-only.
        read_only_root: When ``True``, mount the root filesystem read-only.
        cap_drop: Linux capabilities to drop (``("ALL",)`` by default).
        env: Environment variables to inject into the container.
    """

    image: str
    network: Optional[str] = None
    runtime: Optional[str] = None
    rootless: bool = True
    gpu_ids: tuple[int, ...] = ()
    read_only_root: bool = True
    cap_drop: tuple[str, ...] = ("ALL",)
    env: dict[str, str] = field(default_factory=dict)

    def to_docker_args(self) -> list[str]:
        """Render the privacy/isolation flags for ``docker run``.

        Only the isolation-relevant flags are emitted here (the caller appends
        the image, command, mounts, etc.). ``rootless`` is informational and
        produces no flag.

        Returns:
            A flat list of CLI tokens, e.g.
            ``["--network", "none", "--read-only", "--cap-drop", "ALL"]``.
        """
        args: list[str] = []

        # Network: None => fully sealed (no network namespace connectivity).
        if self.network is None:
            args += ["--network", "none"]
        else:
            args += ["--network", self.network]

        # Alternative sandboxed runtime (gVisor) when configured.
        if self.runtime is not None:
            args += ["--runtime", self.runtime]

        # Immutable root filesystem.
        if self.read_only_root:
            args.append("--read-only")

        # Drop Linux capabilities.
        for cap in self.cap_drop:
            args += ["--cap-drop", cap]

        # GPU exposure (only when GPUs were granted).
        if self.gpu_ids:
            gpu_list = ",".join(str(i) for i in self.gpu_ids)
            args += ["--gpus", f'"device={gpu_list}"']

        return args


def build_container_spec(
    kernel_spec: KernelSpec, *, gvisor: bool = True
) -> ContainerSpec:
    """Build a sealed :class:`ContainerSpec` from a kernel request.

    PRIVACY DEFAULT: if ``kernel_spec.allow_egress`` is ``False`` (the
    default), ``network`` MUST be ``None`` — the container gets no network
    whatsoever. Only when ``allow_egress`` is ``True`` may the container join a
    bridge network, and even then the policy engine must have approved that
    path; the egress gate (:mod:`gadziriro.policy.egress`) remains the single
    source of truth for what any outbound connection may reach.

    Args:
        kernel_spec: The requested kernel configuration.
        gvisor: When ``True``, use the gVisor runtime (``"runsc"``) on the
            target host; otherwise fall back to the default runtime.

    Returns:
        A frozen, hardened :class:`ContainerSpec`.
    """
    if kernel_spec.allow_egress:
        # Egress was explicitly approved. The policy engine MUST have gated the
        # specific destinations before we got here; a bridge only grants the
        # *possibility* of network — the EgressPolicy still decides each target.
        network: Optional[str] = "bridge"
    else:
        # Default, overwhelmingly common path: zero network.
        network = None

    gpu_ids: tuple[int, ...] = (
        kernel_spec.gpu.gpu_ids if kernel_spec.gpu is not None else ()
    )

    return ContainerSpec(
        image=kernel_spec.image,
        network=network,
        runtime="runsc" if gvisor else None,
        rootless=True,
        gpu_ids=gpu_ids,
        read_only_root=True,
        cap_drop=("ALL",),
        env=dict(kernel_spec.env),
    )
