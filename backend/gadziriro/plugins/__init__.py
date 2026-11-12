"""Gadziriro plug-in kit (Phase 4, FR-32)."""

from .kit import (
    PluginBundle,
    PluginError,
    PluginKind,
    PluginManifest,
    PluginRecord,
    PluginRegistry,
    SandboxSpec,
    sign_plugin,
    verify_plugin,
)

__all__ = [
    "PluginBundle",
    "PluginError",
    "PluginKind",
    "PluginManifest",
    "PluginRecord",
    "PluginRegistry",
    "SandboxSpec",
    "sign_plugin",
    "verify_plugin",
]
