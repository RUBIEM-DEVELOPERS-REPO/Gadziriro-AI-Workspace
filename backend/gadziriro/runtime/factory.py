"""Runtime backend selection.

The control plane asks the factory for a :class:`RuntimeAdapter`; the concrete
backend is chosen by ``Settings.runtime_backend`` ("mock" or "docker"). The
docker backend is imported lazily so selecting "mock" never pulls in Docker.
"""

from __future__ import annotations

from ..core.config import Settings
from ..core.errors import RuntimeAdapterError
from .base import RuntimeAdapter
from .mock import MockRuntimeAdapter


def get_runtime_adapter(settings: Settings) -> RuntimeAdapter:
    """Return the runtime adapter named by ``settings.runtime_backend``.

    :raises RuntimeAdapterError: if the configured backend name is unknown.
    """
    backend = settings.runtime_backend.strip().lower()
    if backend == "mock":
        return MockRuntimeAdapter()
    if backend == "docker":
        # Lazy import: keeps the Docker SDK off the import path unless selected.
        from .docker import DockerRuntimeAdapter

        return DockerRuntimeAdapter(settings=settings)
    raise RuntimeAdapterError(f"unknown runtime backend: {settings.runtime_backend!r}")
