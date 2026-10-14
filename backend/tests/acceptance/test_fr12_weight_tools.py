"""FR-12 acceptance: weight tools (merge, quantize, prune, inspect) end to end.

Every derived model must be traceable to its source(s) via lineage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.governance.labels import SensitivityLabel
from gadziriro.registry.base import LineageRecord
from gadziriro.registry.store import ObjectStoreRegistry
from gadziriro.weighttools import QuantMethod, inspect, merge, prune, quantize


def _registry(tmp_path: Path) -> ObjectStoreRegistry:
    return ObjectStoreRegistry(LocalObjectStore(tmp_path / "store"))


def _seed_base_models(reg: ObjectStoreRegistry) -> None:
    reg.add_dataset(
        "corpus", b"docs", sensitivity=SensitivityLabel.INTERNAL, source="approved"
    )
    reg.add_model(
        "llm_a",
        b"A" * 4096,
        lineage=LineageRecord(dataset_refs=("corpus@1",), code_ref="c1"),
        sensitivity=SensitivityLabel.INTERNAL,
    )
    reg.add_model(
        "llm_b",
        b"B" * 4096,
        lineage=LineageRecord(dataset_refs=("corpus@1",), code_ref="c2"),
        sensitivity=SensitivityLabel.INTERNAL,
    )


def test_fr12_merge_quantize_prune_inspect_end_to_end(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _seed_base_models(reg)

    # 1. Merge two base models.
    merged = merge(reg, ["llm_a@1", "llm_b@1"], "llm_merged", weights=[0.6, 0.4])
    assert merged.ref == "llm_merged@1"
    assert merged.lineage.params["op"] == "merge"
    assert merged.lineage.params["sources"] == ["llm_a@1", "llm_b@1"]

    # 2. Quantize the merged model with each supported method.
    quant_refs: dict[QuantMethod, str] = {}
    for method in (QuantMethod.GPTQ, QuantMethod.AWQ, QuantMethod.GGUF):
        out = f"llm_q_{method.value}"
        q = quantize(reg, "llm_merged@1", method, out)
        assert q.lineage.params == {
            "op": "quantize",
            "method": method.value,
            "source": "llm_merged@1",
        }
        assert q.meta["quantized_bytes"] < q.meta["original_bytes"]
        quant_refs[method] = q.ref

    # 3. Prune one of the quantized models.
    pruned = prune(reg, quant_refs[QuantMethod.GPTQ], 0.4, "llm_pruned")
    assert pruned.lineage.params["op"] == "prune"
    assert pruned.lineage.params["sparsity"] == 0.4
    assert pruned.lineage.params["source"] == quant_refs[QuantMethod.GPTQ]

    # 4. Inspect every derived artifact.
    for ref in ["llm_merged@1", *quant_refs.values(), "llm_pruned@1"]:
        summary = inspect(reg, ref)
        assert summary["size_bytes"] > 0
        assert summary["checksum"]
        assert summary["layers"]
        assert summary["op"] in {"merge", "quantize", "prune"}

    # 5. Traceability: every derived model names its direct source(s) in lineage.
    assert set(reg.get_model("llm_merged").lineage.params["sources"]) == {
        "llm_a@1",
        "llm_b@1",
    }
    assert (
        reg.get_model("llm_pruned").lineage.params["source"]
        == quant_refs[QuantMethod.GPTQ]
    )
    # And the GGUF quantized model traces back to the merge.
    assert reg.get_model("llm_q_gguf").lineage.params["source"] == "llm_merged@1"


def test_fr12_all_derived_models_reach_original_dataset_via_lineage(
    tmp_path: Path,
) -> None:
    """DSAR reach: derived artifacts keep the originating dataset lineage."""
    reg = _registry(tmp_path)
    _seed_base_models(reg)

    merge(reg, ["llm_a@1", "llm_b@1"], "merged")
    quantize(reg, "merged@1", QuantMethod.AWQ, "merged_q")
    prune(reg, "merged_q@1", 0.25, "merged_qp")

    # The original dataset reaches the merged model and every descendant.
    traced = {m.name for m in reg.models_from_dataset("corpus@1")}
    assert {"llm_a", "llm_b", "merged", "merged_q", "merged_qp"} <= traced


def test_fr12_inspect_unknown_ref_raises(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    _seed_base_models(reg)
    from gadziriro.core.errors import NotFound

    with pytest.raises(NotFound):
        inspect(reg, "does_not_exist")
