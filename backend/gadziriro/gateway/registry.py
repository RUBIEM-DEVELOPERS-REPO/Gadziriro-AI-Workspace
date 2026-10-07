"""Router registry — the extension point that lets services self-register.

Each service package (sessions, audit, installer, auth) calls `register_router`
at import time (or is imported by create_app). The gateway mounts whatever is
registered, so adding a service does not mean editing the gateway core.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid a hard FastAPI import for code that only needs the registry
    from fastapi import APIRouter

_ROUTERS: list[tuple[str, "APIRouter"]] = []


def register_router(prefix: str, router: "APIRouter") -> None:
    _ROUTERS.append((prefix, router))


def registered_routers() -> list[tuple[str, "APIRouter"]]:
    return list(_ROUTERS)


def clear_registry() -> None:
    """Test helper."""
    _ROUTERS.clear()
