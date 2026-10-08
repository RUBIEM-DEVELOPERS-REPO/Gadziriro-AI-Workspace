"""Object-store-backed run tracker (FR-09 reproducibility).

Each :class:`~gadziriro.tracking.base.Run` is persisted as a single JSON
document in the shared object store under ``runs/<run_id>.json``. Mutations
(``log_param``, ``log_metric``, ``set_artifact``, ``end_run``) read-modify-write
that document, so a finished run is a durable, self-contained record of the
params, dataset references, code revision and hardware needed to reproduce it.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional

from ..core.errors import NotFound
from ..core.objectstore import ObjectStore
from .base import Run

_RUNS = "runs"


def _now_iso() -> str:
    """Return the current time as an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _run_key(run_id: str) -> str:
    """Return the object-store key for ``run_id``'s JSON document."""
    return f"{_RUNS}/{run_id}.json"


class ObjectStoreTracker:
    """MLflow-style run tracker backed by an :class:`ObjectStore`.

    Implements the :class:`~gadziriro.tracking.base.Tracker` protocol.
    """

    def __init__(self, store: ObjectStore) -> None:
        self._store = store

    # ------------------------------------------------------------------ #
    # (de)serialisation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_dict(run: Run) -> dict[str, Any]:
        """Serialise a :class:`Run` to a JSON-ready dict."""
        return {
            "run_id": run.run_id,
            "status": run.status,
            "params": run.params,
            "metrics": run.metrics,
            "dataset_refs": list(run.dataset_refs),
            "code_ref": run.code_ref,
            "hardware": run.hardware,
            "artifacts": run.artifacts,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
        }

    @staticmethod
    def _from_dict(data: dict[str, Any]) -> Run:
        """Rebuild a :class:`Run` from its stored dict."""
        return Run(
            run_id=data["run_id"],
            status=data["status"],
            params=dict(data.get("params", {})),
            metrics=dict(data.get("metrics", {})),
            dataset_refs=tuple(data.get("dataset_refs", ())),
            code_ref=data.get("code_ref", ""),
            hardware=data.get("hardware", ""),
            artifacts=dict(data.get("artifacts", {})),
            started_at=data.get("started_at", ""),
            ended_at=data.get("ended_at"),
        )

    def _save(self, run: Run) -> None:
        """Persist ``run`` as its JSON document."""
        self._store.put(
            _run_key(run.run_id),
            json.dumps(self._to_dict(run), sort_keys=True).encode("utf-8"),
        )

    def _load(self, run_id: str) -> Run:
        """Load a run by id or raise :class:`NotFound`."""
        key = _run_key(run_id)
        if not self._store.exists(key):
            raise NotFound(f"run not found: {run_id}")
        return self._from_dict(json.loads(self._store.get(key).decode("utf-8")))

    # ------------------------------------------------------------------ #
    # tracker API
    # ------------------------------------------------------------------ #
    def start_run(
        self,
        params: Optional[dict[str, Any]] = None,
        dataset_refs: tuple[str, ...] = (),
        code_ref: str = "",
        hardware: str = "",
    ) -> Run:
        """Open a new run (status ``"running"``) and persist it (FR-09)."""
        run = Run(
            run_id=f"run-{uuid.uuid4().hex[:12]}",
            status="running",
            params=dict(params or {}),
            dataset_refs=tuple(dataset_refs),
            code_ref=code_ref,
            hardware=hardware,
            started_at=_now_iso(),
        )
        self._save(run)
        return run

    def log_param(self, run_id: str, key: str, value: Any) -> None:
        """Record a single parameter on ``run_id``."""
        run = self._load(run_id)
        self._save(replace(run, params={**run.params, key: value}))

    def log_metric(self, run_id: str, key: str, value: Any) -> None:
        """Record a single metric on ``run_id``."""
        run = self._load(run_id)
        self._save(replace(run, metrics={**run.metrics, key: value}))

    def set_artifact(self, run_id: str, name: str, ref: str) -> None:
        """Attach an artifact reference (``name`` -> ``ref``) to ``run_id``."""
        run = self._load(run_id)
        self._save(replace(run, artifacts={**run.artifacts, name: ref}))

    def end_run(self, run_id: str, status: str = "finished") -> Run:
        """Close ``run_id`` with ``status`` and stamp ``ended_at`` (FR-09)."""
        run = self._load(run_id)
        ended = replace(run, status=status, ended_at=_now_iso())
        self._save(ended)
        return ended

    def get_run(self, run_id: str) -> Run:
        """Return the run with ``run_id`` or raise :class:`NotFound`."""
        return self._load(run_id)

    def list_runs(self) -> list[Run]:
        """Return every persisted run (sorted by ``started_at`` then id)."""
        runs: list[Run] = []
        for key in self._store.list(f"{_RUNS}/"):
            if key.endswith(".json"):
                runs.append(
                    self._from_dict(json.loads(self._store.get(key).decode("utf-8")))
                )
        return sorted(runs, key=lambda r: (r.started_at, r.run_id))
