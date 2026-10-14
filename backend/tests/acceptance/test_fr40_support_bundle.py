"""FR-40 acceptance: a support bundle carries no personal data or raw dataset bytes.

A troubleshooting bundle is assembled from a workspace seeded with PII, PHI, and
raw dataset bytes. The produced bundle must be provably free of all of them.
"""

from __future__ import annotations

from pathlib import Path

from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.ops.support_bundle import build_support_bundle

EMAIL = "jane.doe@clinic.example"
RAW_PHI = "RAW-PHI-DIAGNOSIS-PAYLOAD-0xDEADBEEF"
SUBJECT_ID = "subject-xyz-42"


def _seed(root: Path) -> Path:
    data = root / "data"
    (data / "audit").mkdir(parents=True)
    (data / "datasets" / "scans" / "3").mkdir(parents=True)
    (data / "phi").mkdir(parents=True)

    (data / "settings.json").write_text(
        '{"runtime_backend": "mock", "allow_egress": false}', encoding="utf-8"
    )
    (data / "audit" / "audit.jsonl").write_text(
        f'{{"actor":"{EMAIL}","action":"session.start","target":"{SUBJECT_ID}"}}\n',
        encoding="utf-8",
    )
    (data / "datasets" / "scans" / "3" / "blob").write_text(RAW_PHI, encoding="utf-8")
    (data / "phi" / "ward.log").write_text(
        f"{RAW_PHI} for {SUBJECT_ID}", encoding="utf-8"
    )
    return data


def test_fr40_bundle_is_pii_stripped(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    out_store = LocalObjectStore(tmp_path / "out")

    result = build_support_bundle(data_dir=data, out_store=out_store)

    assert out_store.exists(result["bundle_key"])
    assert result["redacted_fields_count"] > 0

    blob = out_store.get(result["bundle_key"]).decode("utf-8")
    assert EMAIL not in blob
    assert RAW_PHI not in blob
    assert SUBJECT_ID not in blob

    # The config summary is present but exposes only key names, not values.
    assert "settings.json" in blob
