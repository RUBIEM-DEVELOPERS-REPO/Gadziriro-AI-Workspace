"""Unit tests for the SBOM generator (NFR-18)."""

from __future__ import annotations

import json

from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.ops.sbom import build_sbom, write_sbom


def test_parses_requirements(tmp_path) -> None:
    req = tmp_path / "r.txt"
    req.write_text(
        "# comment\n\nfastapi>=0.115,<0.116\nuvicorn[standard]>=0.30 # c\n"
        "-r other.txt\npydantic==2.7\n",
        encoding="utf-8",
    )
    sbom = build_sbom(req)
    names = {c["name"]: c for c in sbom["components"]}
    assert set(names) == {"fastapi", "uvicorn", "pydantic"}
    assert names["fastapi"]["version_spec"] == ">=0.115,<0.116"
    assert names["uvicorn"]["extras"] == ["standard"]
    assert sbom["component_count"] == 3
    assert sbom["generated_at"]


def test_default_requirements_has_fastapi() -> None:
    assert "fastapi" in {c["name"] for c in build_sbom()["components"]}


def test_write_sbom(tmp_path) -> None:
    store = LocalObjectStore(tmp_path / "out")
    key = write_sbom(build_sbom(), store)
    assert key == "sbom/sbom.json"
    assert json.loads(store.get(key))["bomFormat"] == "gadziriro-sbom"
