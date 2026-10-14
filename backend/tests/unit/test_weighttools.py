"""Unit tests for weight tools: merge, quantize, prune, inspect (FR-12)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.errors import NotFound
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry
from gadziriro.weighttools import QuantMethod, inspect, merge, prune, quantize


def _registry(tmp_path: Path) -> ObjectStoreRegistry:
    return ObjectStoreRegistry(LocalObjectStore(tmp_path / "store"))


def _seed_two_models(reg: ObjectStoreRegistry) -> None:
    """Register two base model versions, each with its own dataset lineage."""
    reg.add_dataset("ds_a", b"a", sensitivity=SensitivityLabel.INTERNAL, source="s")
    reg.add_dataset("ds_b", b"b", sensitivity=SensitivityLabel.PERSONAL, source="s")
    reg.add_model(
        "base_a",
        b"W" * 2000,
        lineage=LineageRecord(dataset_refs=("ds_a@1",)),
        sensitivity=SensitivityLabel.INTERNAL,
    )
    reg.add_model(
        "base_b",
        b"X" * 2000,
        lineage=LineageRecord(dataset_refs=("ds_b@1",)),
        sensitivity=SensitivityLabel.PERSONAL,
    )


def test_merge_registers_version_with_both_sources_in_lineage(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _seed_two_models(reg)

    merged = merge(reg, ["base_a@1", "base_b@1"], "merged")

    assert merged.name == "merged"
    assert merged.version == 1
    assert merged.lineage.params["op"] == "merge"
    assert merged.lineage.params["sources"] == ["base_a@1", "base_b@1"]
    # Dataset lineage from both sources is carried through (DSAR reach).
    assert set(merged.lineage.dataset_refs) == {"ds_a@1", "ds_b@1"}
    # Strictest source sensitivity wins (default-strict precedence).
    assert merged.sensitivity is SensitivityLabel.PERSONAL
    # Persisted and re-fetchable.
    assert reg.get_model("merged", 1).lineage.params["sources"] == [
        "base_a@1",
        "base_b@1",
    ]


def test_merge_requires_two_sources(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _seed_two_models(reg)
    from gadziriro.core.errors import GadziriroError

    with pytest.raises(GadziriroError):
        merge(reg, ["base_a@1"], "oops")


def test_merge_weights_change_the_artifact(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _seed_two_models(reg)

    equal = merge(reg, ["base_a@1", "base_b@1"], "m_eq")
    weighted = merge(reg, ["base_a@1", "base_b@1"], "m_wt", weights=[0.7, 0.3])

    assert weighted.lineage.params["weights"] == [0.7, 0.3]
    assert equal.checksum != weighted.checksum


def test_quantize_produces_smaller_tagged_artifact(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _seed_two_models(reg)

    quant = quantize(reg, "base_a@1", QuantMethod.GPTQ, "q_gptq")

    assert quant.lineage.params == {
        "op": "quantize",
        "method": "gptq",
        "source": "base_a@1",
    }
    # Simulated shrink: fewer bytes than the source, recorded in meta.
    assert quant.meta["quantized_bytes"] < quant.meta["original_bytes"]
    assert quant.meta["size_reduction"] > 0.0
    assert inspect(reg, "q_gptq")["size_bytes"] < inspect(reg, "base_a@1")["size_bytes"]
    # Source lineage survives for traceability / DSAR.
    assert quant.lineage.dataset_refs == ("ds_a@1",)


def test_prune_records_sparsity_and_source(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _seed_two_models(reg)

    pruned = prune(reg, "base_a@1", 0.5, "pruned")

    assert pruned.lineage.params == {
        "op": "prune",
        "sparsity": 0.5,
        "source": "base_a@1",
    }
    assert pruned.meta["retained"] == pytest.approx(0.5, abs=0.01)
    assert pruned.lineage.dataset_refs == ("ds_a@1",)


def test_prune_rejects_out_of_range_sparsity(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _seed_two_models(reg)
    from gadziriro.core.errors import GadziriroError

    with pytest.raises(GadziriroError):
        prune(reg, "base_a@1", 1.5, "bad")


def test_inspect_returns_size_checksum_layers_and_op(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _seed_two_models(reg)
    quantize(reg, "base_a@1", QuantMethod.AWQ, "q_awq")

    base = inspect(reg, "base_a@1")
    assert base["size_bytes"] == 2000
    assert base["checksum"] == reg.get_model("base_a", 1).checksum
    assert base["layers"] and base["num_layers"] == len(base["layers"])
    assert base["param_count"] == sum(la["params"] for la in base["layers"])
    # A base model has no producing op.
    assert base["op"] is None

    derived = inspect(reg, "q_awq")
    assert derived["op"] == "quantize"


def test_unknown_ref_raises_notfound(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _seed_two_models(reg)

    with pytest.raises(NotFound):
        inspect(reg, "ghost")
    with pytest.raises(NotFound):
        quantize(reg, "base_a@99", QuantMethod.GGUF, "x")
    with pytest.raises(NotFound):
        prune(reg, "base_a@notanint", 0.1, "x")
    with pytest.raises(NotFound):
        merge(reg, ["base_a@1", "ghost@1"], "x")


def test_operations_are_deterministic(tmp_path: Path) -> None:
    """Same source bytes + same params => same output checksum across stores."""
    reg1 = _registry(tmp_path / "one")
    reg2 = _registry(tmp_path / "two")
    _seed_two_models(reg1)
    _seed_two_models(reg2)

    assert (
        merge(reg1, ["base_a@1", "base_b@1"], "m").checksum
        == merge(reg2, ["base_a@1", "base_b@1"], "m").checksum
    )
    assert (
        quantize(reg1, "base_a@1", QuantMethod.GGUF, "q").checksum
        == quantize(reg2, "base_a@1", QuantMethod.GGUF, "q").checksum
    )
    assert (
        prune(reg1, "base_a@1", 0.3, "p").checksum
        == prune(reg2, "base_a@1", 0.3, "p").checksum
    )
