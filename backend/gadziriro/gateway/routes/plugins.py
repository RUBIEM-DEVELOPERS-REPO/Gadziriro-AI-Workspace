"""Plug-in kit routes (FR-32) — admin only.

* ``GET  /api/plugins`` — list installed plug-ins.
* ``POST /api/plugins/install`` — install a SIGNED bundle (unsigned/tampered refused).
* ``POST /api/plugins/{name}/enable`` / ``/disable`` — toggle a plug-in.
"""

from __future__ import annotations

import base64
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...auth.base import Principal, Role
from ...core.errors import GadziriroError
from ...plugins.kit import PluginBundle
from ..deps import get_plugin_registry, require_role
from ..registry import register_router

router = APIRouter(tags=["plugins"])

_require_admin = require_role(Role.ADMIN)


class PluginInstallIn(BaseModel):
    """A signed plug-in bundle: manifest + base64 payload + base64 signature."""

    manifest: dict[str, Any]
    payload_b64: str = ""
    sig: str = Field(..., description="base64 Ed25519 signature over the manifest")


def _record_out(rec: Any) -> dict[str, Any]:
    m = rec.manifest
    return {
        "name": m.name,
        "kind": m.kind.value if hasattr(m.kind, "value") else m.kind,
        "version": m.version,
        "api_version": m.api_version,
        "enabled": rec.enabled,
        "sandbox": {
            "isolated": rec.sandbox.isolated,
            "network": rec.sandbox.network,
            "executed_by_kit": rec.sandbox.executed_by_kit,
        },
    }


@router.get("")
def list_plugins(
    reg: Annotated[Any, Depends(get_plugin_registry)],
    _: Annotated[Principal, Depends(_require_admin)],
) -> list[dict[str, Any]]:
    """List installed plug-ins."""
    return [_record_out(r) for r in reg.list_plugins()]


@router.post("/install")
def install_plugin(
    body: PluginInstallIn,
    reg: Annotated[Any, Depends(get_plugin_registry)],
    _: Annotated[Principal, Depends(_require_admin)],
) -> dict[str, Any]:
    """Install a signed plug-in; an unsigned/tampered bundle is refused (400)."""
    try:
        payload = base64.b64decode(body.payload_b64) if body.payload_b64 else b""
    except (ValueError, TypeError) as exc:
        raise GadziriroError("payload_b64 is not valid base64") from exc
    bundle = PluginBundle(manifest=body.manifest, payload=payload, sig=body.sig)
    manifest = reg.install(bundle)
    return {"name": manifest.name, "installed": True, "enabled": False}


@router.post("/{name}/enable")
def enable_plugin(
    name: str,
    reg: Annotated[Any, Depends(get_plugin_registry)],
    _: Annotated[Principal, Depends(_require_admin)],
) -> dict[str, Any]:
    """Enable an installed plug-in."""
    return _record_out(reg.enable(name))


@router.post("/{name}/disable")
def disable_plugin(
    name: str,
    reg: Annotated[Any, Depends(get_plugin_registry)],
    _: Annotated[Principal, Depends(_require_admin)],
) -> dict[str, Any]:
    """Disable an installed plug-in."""
    return _record_out(reg.disable(name))


register_router("/api/plugins", router)
