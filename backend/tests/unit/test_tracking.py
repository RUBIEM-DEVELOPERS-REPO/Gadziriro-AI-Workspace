"""Unit tests for the object-store-backed run tracker (FR-09)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.errors import NotFound
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.tracking.store import ObjectStoreTracker


def _tracker(tmp_path: Path) -> ObjectStoreTracker:
    return ObjectStoreTracker(LocalObjectStore(tmp_path / "store"))


def test_start_log_end_run_roundtrip(tmp_path: Path) -> None:
    tr = _tracker(tmp_path)
    run = tr.start_run(
        params={"seed": 7},
        dataset_refs=("ds@1",),
        code_ref="deadbeef",
        hardware="1xA100-80GB",
    )
    assert run.status == "running"
    assert run.started_at
    assert run.ended_at is None

    tr.log_param(run.run_id, "lr", 0.01)
    tr.log_metric(run.run_id, "loss", 0.42)
    tr.set_artifact(run.run_id, "model", "m@1")
    ended = tr.end_run(run.run_id)

    assert ended.status == "finished"
    assert ended.ended_at

    got = tr.get_run(run.run_id)
    assert got.params == {"seed": 7, "lr": 0.01}
    assert got.metrics == {"loss": 0.42}
    assert got.artifacts == {"model": "m@1"}
    assert got.dataset_refs == ("ds@1",)
    assert got.code_ref == "deadbeef"
    assert got.hardware == "1xA100-80GB"
    assert got.status == "finished"


def test_end_run_custom_status(tmp_path: Path) -> None:
    tr = _tracker(tmp_path)
    run = tr.start_run()
    ended = tr.end_run(run.run_id, status="failed")
    assert ended.status == "failed"


def test_list_runs(tmp_path: Path) -> None:
    tr = _tracker(tmp_path)
    a = tr.start_run(params={"i": 1})
    b = tr.start_run(params={"i": 2})
    ids = {r.run_id for r in tr.list_runs()}
    assert ids == {a.run_id, b.run_id}


def test_notfound_on_unknown_run(tmp_path: Path) -> None:
    tr = _tracker(tmp_path)
    with pytest.raises(NotFound):
        tr.get_run("run-nope")
    with pytest.raises(NotFound):
        tr.log_param("run-nope", "k", 1)
    with pytest.raises(NotFound):
        tr.end_run("run-nope")
