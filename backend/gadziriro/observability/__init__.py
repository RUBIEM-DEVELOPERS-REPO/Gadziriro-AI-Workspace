"""Observability: metrics, a Prometheus text exposition, and event emission.

A tiny, dependency-free metrics layer (no ``prometheus_client``) plus a
structured event emitter that is the local export seam to a customer's SIEM
(logs/traces). Nothing here ever touches the network (privacy default).
"""

from __future__ import annotations

from .metrics import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    MetricsRegistry,
    emit_event,
    render_prometheus,
    snapshot_runtime,
)

__all__ = [
    "CONTENT_TYPE_LATEST",
    "Counter",
    "Gauge",
    "MetricsRegistry",
    "emit_event",
    "render_prometheus",
    "snapshot_runtime",
]
