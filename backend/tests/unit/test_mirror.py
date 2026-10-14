"""Unit tests for the approved-only mirror + scanning proxy (FR-29, NFR-12)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.crypto import sha256_hex
from gadziriro.core.errors import NotFound, PolicyDenied
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.mirror.base import PackageMirror, SignatureScanner
from gadziriro.mirror.store import ObjectStoreMirror


def _mirror(tmp_path: Path, **kwargs) -> ObjectStoreMirror:
    return ObjectStoreMirror(LocalObjectStore(tmp_path / "mirror"), **kwargs)


def test_implements_package_mirror(tmp_path: Path) -> None:
    assert isinstance(_mirror(tmp_path), PackageMirror)


def test_add_then_has_and_get_round_trip(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    data = b"def hello(): return 42\n"

    meta = mirror.add_package("acme", "1.2.3", data)

    assert mirror.has_package("acme", "1.2.3") is True
    assert mirror.get_package("acme", "1.2.3") == data
    # Checksum recorded in meta matches the artifact bytes.
    assert meta["sha256"] == sha256_hex(data)
    assert mirror.package_meta("acme", "1.2.3")["sha256"] == sha256_hex(data)
    assert meta["size"] == len(data)


def test_get_unknown_package_raises_notfound_no_network(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    # Nothing was added => NotFound, never a network fetch. That is the point.
    assert mirror.has_package("nope", "0.0.1") is False
    with pytest.raises(NotFound):
        mirror.get_package("nope", "0.0.1")


def test_scanner_blocks_bad_signature_and_stores_nothing(tmp_path: Path) -> None:
    scanner = SignatureScanner(bad_signatures=(b"BADSIG",))
    mirror = _mirror(tmp_path, scanner=scanner)

    with pytest.raises(PolicyDenied):
        mirror.add_package("evil", "6.6.6", b"payload with BADSIG inside")

    # Blocked artifact left no trace at all.
    assert mirror.has_package("evil", "6.6.6") is False
    with pytest.raises(NotFound):
        mirror.get_package("evil", "6.6.6")
    assert mirror.list_packages() == []


def test_list_packages_reflects_contents(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    mirror.add_package("alpha", "1.0.0", b"a")
    mirror.add_package("beta", "2.0.0", b"b")
    mirror.add_package("alpha", "1.1.0", b"a2")

    assert mirror.list_packages() == [
        ("alpha", "1.0.0"),
        ("alpha", "1.1.0"),
        ("beta", "2.0.0"),
    ]


def test_models_round_trip_independently(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    mirror.add_model("llama", "8b", b"weights")

    assert mirror.has_model("llama", "8b") is True
    assert mirror.get_model("llama", "8b") == b"weights"
    assert mirror.list_models() == [("llama", "8b")]
    # Models and packages share no namespace.
    assert mirror.has_package("llama", "8b") is False
    assert mirror.list_packages() == []
