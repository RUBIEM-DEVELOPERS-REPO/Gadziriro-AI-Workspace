"""Phase 0 acceptance: notebooks + sealed sessions (FR-01, FR-02, FR-03).

Runs entirely against the mock runtime backend, so it passes on any host. The
kernel-level container/GPU acceptance is covered by the target_hardware tests.
"""

from __future__ import annotations

from pathlib import Path

from gadziriro.runtime.mock import MockRuntimeAdapter
from gadziriro.sessions.manager import SessionManager
from gadziriro.sessions.notebook import load_notebook, save_notebook

SAMPLE_NOTEBOOK = {
    "cells": [
        {
            "cell_type": "code",
            "execution_count": 1,
            "metadata": {"tags": ["keep"]},
            "outputs": [],
            "source": ["print('hello')\n"],
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["# Title\n", "Some text.\n"],
        },
    ],
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.11.0"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}


def test_fr02_ipynb_round_trips_unchanged(tmp_path: Path) -> None:
    p = tmp_path / "demo.ipynb"
    save_notebook(p, SAMPLE_NOTEBOOK)
    loaded = load_notebook(p)
    # Cells and metadata must be preserved exactly (no upgrade/normalisation).
    assert loaded == SAMPLE_NOTEBOOK
    assert loaded["cells"][0]["metadata"]["tags"] == ["keep"]
    assert loaded["nbformat"] == 4


def test_fr03_each_session_is_sealed_with_its_own_gpu() -> None:
    adapter = MockRuntimeAdapter(gpu_count=2, gpu_memory_mb=24000)
    mgr = SessionManager(adapter)
    a = mgr.create_session("a", user="u1", gpu_memory_mb=24000)
    b = mgr.create_session("b", user="u2", gpu_memory_mb=24000)
    # Distinct kernels, disjoint GPUs, and no network by default (sealed).
    assert a.kernel_id != b.kernel_id
    assert set(a.gpu_ids).isdisjoint(b.gpu_ids)
    assert a.allow_egress is False and b.allow_egress is False
    rec_a = adapter.kernel_record(a.kernel_id)
    assert rec_a.network_enabled is False


def test_fr01_run_a_cell_and_get_output() -> None:
    mgr = SessionManager(MockRuntimeAdapter(gpu_count=1))
    mgr.create_session("s1", user="alice")
    result = mgr.run_cell("s1", "40 + 2")
    assert result["output"] == "42"
