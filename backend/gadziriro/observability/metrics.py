"""A tiny, dependency-free metrics + event layer for observability (FR-39).

This provides just enough to expose operational signals without pulling in
``prometheus_client``:

* :class:`Counter` and :class:`Gauge` -- labelled metric types held in a
  :class:`MetricsRegistry`.
* :func:`render_prometheus` -- renders the registry in the Prometheus text
  exposition format (``# HELP`` / ``# TYPE`` lines + samples), suitable to serve
  as ``Content-Type: text/plain; version=0.0.4``.
* :func:`snapshot_runtime` -- maps a :class:`~gadziriro.runtime.base.RuntimeMetrics`
  onto the four ``gadziriro_*`` runtime gauges.
* :func:`emit_event` -- a structured event record (the local export seam to the
  customer's SIEM for logs/traces).

Everything is local; nothing here opens a socket (privacy default).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Tuple

CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

# Internal label-value key: a tuple of values ordered to match ``labelnames``.
_LabelKey = Tuple[str, ...]


def _escape_help(text: str) -> str:
    """Escape a metric help string per the Prometheus exposition format."""
    return text.replace("\\", "\\\\").replace("\n", "\\n")


def _escape_label_value(value: str) -> str:
    """Escape a label value per the Prometheus exposition format."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class _Metric:
    """Base class for a single named, labelled metric series collection."""

    type_name = "untyped"

    def __init__(
        self, name: str, documentation: str, labelnames: Iterable[str] = ()
    ) -> None:
        """Create a metric family.

        Args:
            name: Metric name (e.g. ``gadziriro_jobs_running``).
            documentation: Human-readable ``# HELP`` text.
            labelnames: Ordered label names shared by every sample.
        """
        self.name = name
        self.documentation = documentation
        self.labelnames: Tuple[str, ...] = tuple(labelnames)
        self._values: Dict[_LabelKey, float] = {}

    def _key(self, labels: Dict[str, str]) -> _LabelKey:
        """Validate and order a label mapping into a stable key tuple."""
        if set(labels) != set(self.labelnames):
            raise ValueError(
                f"metric {self.name!r} expects labels {self.labelnames}, "
                f"got {tuple(labels)}"
            )
        return tuple(str(labels[name]) for name in self.labelnames)

    def samples(self) -> Iterable[Tuple[Dict[str, str], float]]:
        """Yield ``(labels, value)`` pairs for every stored series."""
        for key, value in self._values.items():
            labels = dict(zip(self.labelnames, key, strict=False))
            yield labels, value


class Counter(_Metric):
    """A monotonically increasing counter."""

    type_name = "counter"

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        """Increment the series for ``labels`` by ``amount`` (default 1).

        Args:
            amount: Non-negative increment.
            labels: Values for this metric's label names.

        Raises:
            ValueError: if ``amount`` is negative or labels do not match.
        """
        if amount < 0:
            raise ValueError("Counter.inc amount must be non-negative")
        key = self._key(labels)
        self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, **labels: str) -> float:
        """Return the current value for ``labels`` (0.0 if never incremented)."""
        return self._values.get(self._key(labels), 0.0)


class Gauge(_Metric):
    """A value that can go up or down."""

    type_name = "gauge"

    def set(self, value: float, **labels: str) -> None:
        """Set the series for ``labels`` to ``value``."""
        self._values[self._key(labels)] = float(value)

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        """Increment the series for ``labels`` by ``amount``."""
        key = self._key(labels)
        self._values[key] = self._values.get(key, 0.0) + amount

    def dec(self, amount: float = 1.0, **labels: str) -> None:
        """Decrement the series for ``labels`` by ``amount``."""
        self.inc(-amount, **labels)

    def value(self, **labels: str) -> float:
        """Return the current value for ``labels`` (0.0 if never set)."""
        return self._values.get(self._key(labels), 0.0)


class MetricsRegistry:
    """Holds a set of uniquely-named metrics and renders them together."""

    def __init__(self) -> None:
        self._metrics: Dict[str, _Metric] = {}

    def register(self, metric: _Metric) -> _Metric:
        """Register ``metric``; raise if its name is already taken."""
        if metric.name in self._metrics:
            raise ValueError(f"metric already registered: {metric.name}")
        self._metrics[metric.name] = metric
        return metric

    def counter(
        self, name: str, documentation: str, labelnames: Iterable[str] = ()
    ) -> Counter:
        """Get the existing :class:`Counter` ``name`` or create and register it."""
        existing = self._metrics.get(name)
        if isinstance(existing, Counter):
            return existing
        if existing is not None:
            raise ValueError(f"metric {name!r} is not a Counter")
        return self.register(Counter(name, documentation, labelnames))  # type: ignore[return-value]

    def gauge(
        self, name: str, documentation: str, labelnames: Iterable[str] = ()
    ) -> Gauge:
        """Get the existing :class:`Gauge` ``name`` or create and register it."""
        existing = self._metrics.get(name)
        if isinstance(existing, Gauge):
            return existing
        if existing is not None:
            raise ValueError(f"metric {name!r} is not a Gauge")
        return self.register(Gauge(name, documentation, labelnames))  # type: ignore[return-value]

    def collect(self) -> Iterable[_Metric]:
        """Yield the registered metrics in registration order."""
        return list(self._metrics.values())


def _format_labels(labels: Dict[str, str]) -> str:
    """Render a label mapping as ``{k="v",...}`` (empty string if no labels)."""
    if not labels:
        return ""
    inner = ",".join(
        f'{name}="{_escape_label_value(value)}"' for name, value in labels.items()
    )
    return "{" + inner + "}"


def _format_number(value: float) -> str:
    """Render a float without a trailing ``.0`` when it is integral."""
    if value == int(value):
        return str(int(value))
    return repr(value)


def render_prometheus(registry: MetricsRegistry) -> str:
    """Render ``registry`` in the Prometheus text exposition format.

    Each metric contributes a ``# HELP`` line, a ``# TYPE`` line, and one sample
    line per label series. The returned text is suitable to serve as
    :data:`CONTENT_TYPE_LATEST`.

    Args:
        registry: The registry whose metrics to render.

    Returns:
        The exposition text (trailing newline included).
    """
    lines: list[str] = []
    for metric in registry.collect():
        lines.append(f"# HELP {metric.name} {_escape_help(metric.documentation)}")
        lines.append(f"# TYPE {metric.name} {metric.type_name}")
        for labels, value in metric.samples():
            lines.append(
                f"{metric.name}{_format_labels(labels)} {_format_number(value)}"
            )
    return "\n".join(lines) + "\n"


def snapshot_runtime(registry: MetricsRegistry, runtime_metrics: Any) -> None:
    """Set the four ``gadziriro_*`` runtime gauges from a ``RuntimeMetrics``.

    Args:
        registry: The registry to populate (gauges are created if absent).
        runtime_metrics: A :class:`~gadziriro.runtime.base.RuntimeMetrics`
            (or any object exposing the same four integer attributes).
    """
    registry.gauge("gadziriro_gpus_total", "Total GPUs known to the runtime").set(
        runtime_metrics.gpus_total
    )
    registry.gauge("gadziriro_gpus_free", "GPUs currently free").set(
        runtime_metrics.gpus_free
    )
    registry.gauge(
        "gadziriro_kernels_running", "Notebook kernels currently running"
    ).set(runtime_metrics.kernels_running)
    registry.gauge("gadziriro_jobs_running", "Background jobs currently running").set(
        runtime_metrics.jobs_running
    )


def emit_event(kind: str, **fields: Any) -> Dict[str, Any]:
    """Build a structured, JSON-serialisable event record (logs/traces seam).

    This is the local export seam to the customer's SIEM: callers persist or
    forward the returned record through their own sink. No network I/O happens
    here (privacy default).

    Args:
        kind: The event kind/name (e.g. ``"backup.completed"``).
        fields: Arbitrary JSON-serialisable context for the event.

    Returns:
        A dict with ``ts`` (UTC ISO-8601), ``kind``, and ``fields``.
    """
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "fields": dict(fields),
    }
