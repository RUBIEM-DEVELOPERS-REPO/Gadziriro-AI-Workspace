"""Gateway route modules.

Importing this package imports each route module, so every router registers
itself with :mod:`gadziriro.gateway.registry` as a side effect. ``create_app``
imports this package and mounts whatever registered.
"""

from __future__ import annotations

from . import (
    audit,
    auth,
    backup,
    exports,
    governance,
    installer,
    jobs,
    metrics,
    mfa,
    mirror,
    registry,
    sessions,
)

__all__ = [
    "audit",
    "auth",
    "backup",
    "exports",
    "governance",
    "installer",
    "jobs",
    "metrics",
    "mfa",
    "mirror",
    "registry",
    "sessions",
]
