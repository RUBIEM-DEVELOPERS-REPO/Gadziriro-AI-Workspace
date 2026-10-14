"""Run-tracking contract (FR-09 reproducibility).

An MLflow-style run captures everything needed to reproduce a training or
evaluation job: the parameters, the exact dataset references, the code revision
and the hardware it ran on. A *finished* run is therefore a self-contained
reproducibility record that pairs with the registry's lineage (FR-07).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass(frozen=True)
class Run:
    """A single tracked run.

    ``status`` is ``"running"`` while open and ``"finished"`` (or another
    terminal status such as ``"failed"``) once ended. ``params``,
    ``dataset_refs``, ``code_ref`` and ``hardware`` together make a finished run
    reproducible (FR-09); ``metrics`` and ``artifacts`` record its outputs.
    """

    run_id: str
    status: str
    params: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    dataset_refs: tuple[str, ...] = ()
    code_ref: str = ""
    hardware: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    started_at: str = ""
    ended_at: Optional[str] = None


class Tracker(Protocol):
    """Records runs and their params/metrics/artifacts for reproducibility."""

    def start_run(
        self,
        params: Optional[dict[str, Any]] = None,
        dataset_refs: tuple[str, ...] = (),
        code_ref: str = "",
        hardware: str = "",
    ) -> Run: ...

    def log_param(self, run_id: str, key: str, value: Any) -> None: ...

    def log_metric(self, run_id: str, key: str, value: Any) -> None: ...

    def set_artifact(self, run_id: str, name: str, ref: str) -> None: ...

    def end_run(self, run_id: str, status: str = "finished") -> Run: ...

    def get_run(self, run_id: str) -> Run: ...

    def list_runs(self) -> list[Run]: ...
