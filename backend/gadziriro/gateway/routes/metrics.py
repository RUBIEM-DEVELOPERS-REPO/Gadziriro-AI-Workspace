"""Prometheus metrics endpoint (FR-39).

``GET /metrics`` (deliberately **not** under ``/api``) renders the injected
:class:`~gadziriro.observability.metrics.MetricsRegistry` in the Prometheus text
exposition format. Before rendering, the four ``gadziriro_*`` runtime gauges are
refreshed from the session manager's runtime adapter metrics.

Auth choice: this endpoint is left **unauthenticated** so a Prometheus scraper
can read it without a session cookie — the standard pattern for ``/metrics``.
It exposes only aggregate operational gauges (no principal or payload data). In
a hardened deployment it is expected to be reached over the cluster-internal
network only (or fronted by a scrape token at the reverse proxy); that is an
infrastructure concern, not an application one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from ...observability.metrics import (
    CONTENT_TYPE_LATEST,
    MetricsRegistry,
    render_prometheus,
    snapshot_runtime,
)
from ...sessions.manager import SessionManager
from ..deps import get_metrics, get_session_manager
from ..registry import register_router

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def metrics(
    registry: Annotated[MetricsRegistry, Depends(get_metrics)],
    manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> PlainTextResponse:
    """Render the metrics registry as Prometheus text (unauthenticated)."""
    adapter = getattr(manager, "_adapter", None)
    if adapter is not None:
        snapshot_runtime(registry, adapter.metrics())
    return PlainTextResponse(
        render_prometheus(registry), media_type=CONTENT_TYPE_LATEST
    )


register_router("", router)
