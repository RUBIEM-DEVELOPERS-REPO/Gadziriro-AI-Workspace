"""Runtime configuration.

Single-node defaults, overridable by environment variables (prefix GADZIRIRO_).
Privacy-first defaults: NO egress, NO telemetry (NFR-01, NFR-02).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(f"GADZIRIRO_{name}", default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(f"GADZIRIRO_{name}")
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Where all workspace state lives (encrypted disk on the target host).
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", ".gadziriro")))
    # SQLite by default (single-node, zero-config); Postgres later (ADR-0005).
    database_url: str = field(
        default_factory=lambda: _env("DATABASE_URL", "sqlite:///./gadziriro.db")
    )
    # Runtime backend: "mock" (default, testable anywhere) or "docker" (target).
    runtime_backend: str = field(
        default_factory=lambda: _env("RUNTIME_BACKEND", "mock")
    )
    # Privacy: no outbound internet from user code unless an admin opens it (FR-20).
    allow_egress: bool = field(default_factory=lambda: _env_bool("ALLOW_EGRESS", False))
    # Privacy: never phone home (NFR-02).
    telemetry_enabled: bool = field(
        default_factory=lambda: _env_bool("TELEMETRY_ENABLED", False)
    )
    # Idle session GPU reclaim (seconds); Phase 1 scheduler refines this (FR-04).
    session_idle_timeout_s: int = field(
        default_factory=lambda: int(_env("SESSION_IDLE_TIMEOUT_S", "1800"))
    )

    @property
    def audit_dir(self) -> Path:
        return self.data_dir / "audit"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audit_dir.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    return Settings()
