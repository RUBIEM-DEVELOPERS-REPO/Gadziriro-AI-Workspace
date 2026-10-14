"""Unit tests for the observability metrics + event layer (FR-39)."""

from __future__ import annotations

from gadziriro.observability.metrics import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    MetricsRegistry,
    emit_event,
    render_prometheus,
    snapshot_runtime,
)
from gadziriro.runtime.base import RuntimeMetrics


def test_counter_increments() -> None:
    reg = MetricsRegistry()
    c = reg.counter("gadziriro_jobs_total", "Jobs started", ["status"])
    c.inc(status="succeeded")
    c.inc(2, status="succeeded")
    c.inc(status="failed")

    assert c.value(status="succeeded") == 3
    assert c.value(status="failed") == 1
    assert isinstance(c, Counter)


def test_gauge_set_inc_dec() -> None:
    reg = MetricsRegistry()
    g = reg.gauge("gadziriro_queue_depth", "Queued items")
    g.set(5)
    g.inc(2)
    g.dec()
    assert g.value() == 6
    assert isinstance(g, Gauge)


def test_render_prometheus_has_help_type_and_samples() -> None:
    reg = MetricsRegistry()
    c = reg.counter("gadziriro_jobs_total", "Jobs started", ["status"])
    c.inc(3, status="succeeded")

    text = render_prometheus(reg)
    assert "# HELP gadziriro_jobs_total Jobs started" in text
    assert "# TYPE gadziriro_jobs_total counter" in text
    assert 'gadziriro_jobs_total{status="succeeded"} 3' in text
    assert "version=0.0.4" in CONTENT_TYPE_LATEST


def test_snapshot_runtime_populates_four_gauges() -> None:
    reg = MetricsRegistry()
    rm = RuntimeMetrics(gpus_total=8, gpus_free=3, kernels_running=5, jobs_running=2)
    snapshot_runtime(reg, rm)

    text = render_prometheus(reg)
    assert "gadziriro_gpus_total 8" in text
    assert "gadziriro_gpus_free 3" in text
    assert "gadziriro_kernels_running 5" in text
    assert "gadziriro_jobs_running 2" in text

    # Re-snapshotting updates (does not duplicate) the same gauges.
    snapshot_runtime(
        reg,
        RuntimeMetrics(gpus_total=8, gpus_free=1, kernels_running=7, jobs_running=4),
    )
    text2 = render_prometheus(reg)
    assert "gadziriro_gpus_free 1" in text2
    assert text2.count("# TYPE gadziriro_gpus_free gauge") == 1


def test_emit_event_returns_record_with_ts_kind_fields() -> None:
    event = emit_event("backup.completed", backup_id="abc", files=3)
    assert set(event) == {"ts", "kind", "fields"}
    assert event["kind"] == "backup.completed"
    assert event["fields"] == {"backup_id": "abc", "files": 3}
    assert isinstance(event["ts"], str) and event["ts"]
