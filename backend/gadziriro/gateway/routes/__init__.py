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
    compliance,
    datasetacl,
    dsar,
    evaluation,
    evidence,
    exports,
    governance,
    incident,
    installer,
    jobs,
    licensing,
    metrics,
    mfa,
    mirror,
    modelcards,
    modelstudio,
    plugins,
    policypacks,
    registry,
    reports,
    safety,
    sessions,
    support,
    updates,
    weighttools,
)

__all__ = [
    "audit",
    "auth",
    "backup",
    "compliance",
    "datasetacl",
    "dsar",
    "evaluation",
    "evidence",
    "exports",
    "governance",
    "incident",
    "installer",
    "jobs",
    "licensing",
    "metrics",
    "mfa",
    "mirror",
    "modelcards",
    "modelstudio",
    "plugins",
    "policypacks",
    "registry",
    "reports",
    "safety",
    "sessions",
    "support",
    "updates",
    "weighttools",
]
