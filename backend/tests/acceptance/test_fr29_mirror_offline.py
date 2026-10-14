"""Acceptance: FR-29 -- the workspace is served ONLY from the local mirror.

Scenario: the workspace is air-gapped. A package can be obtained only after an
admin has added it to the mirror; an artifact that was never added cannot be
obtained at all (NotFound) -- the workspace never reaches outside for it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gadziriro.core.errors import NotFound
from gadziriro.core.objectstore import LocalObjectStore
from gadziriro.mirror.store import ObjectStoreMirror


def _mirror(tmp_path: Path) -> ObjectStoreMirror:
    return ObjectStoreMirror(LocalObjectStore(tmp_path / "mirror"))


def test_package_served_only_after_admin_adds_it(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    wheel = b"PK\x03\x04 ... fake wheel bytes ..."

    # Before the admin adds it, the workspace cannot obtain the package.
    assert mirror.has_package("pandas", "2.2.0") is False
    with pytest.raises(NotFound):
        mirror.get_package("pandas", "2.2.0")

    # Admin approves + adds it to the mirror.
    mirror.add_package("pandas", "2.2.0", wheel)

    # Now (and only now) the workspace is served the artifact -- from local disk.
    assert mirror.has_package("pandas", "2.2.0") is True
    assert mirror.get_package("pandas", "2.2.0") == wheel


def test_unadded_package_is_never_reachable(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    # A different package IS mirrored...
    mirror.add_package("numpy", "1.26.0", b"approved")

    # ...but an un-added one is not fetched from anywhere: NotFound, no egress.
    assert mirror.has_package("requests", "2.31.0") is False
    with pytest.raises(NotFound):
        mirror.get_package("requests", "2.31.0")
