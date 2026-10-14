"""Unit tests for repeatable, mirror-served environment specs (FR-34)."""

from __future__ import annotations

import pytest

from gadziriro.environments import EnvironmentSpec, UnresolvedEnvironment


class FakeMirror:
    """Structural mirror: knows a fixed set of (name, version) pairs."""

    def __init__(self, available: set[tuple[str, str]]) -> None:
        self._available = set(available)

    def has_package(self, name: str, version: str) -> bool:
        return (name, version) in self._available


PINS = {"torch": "2.3.1", "numpy": "1.26.4"}


def test_lock_hash_stable_for_same_pins() -> None:
    a = EnvironmentSpec(name="env", packages=dict(PINS))
    # Different dict insertion order, same logical pins.
    b = EnvironmentSpec(name="env", packages={"numpy": "1.26.4", "torch": "2.3.1"})
    assert a.lock_hash() == b.lock_hash()


def test_lock_hash_changes_when_version_changes() -> None:
    a = EnvironmentSpec(name="env", packages=dict(PINS))
    bumped = dict(PINS)
    bumped["numpy"] = "1.26.5"
    b = EnvironmentSpec(name="env", packages=bumped)
    assert a.lock_hash() != b.lock_hash()


def test_lock_hash_changes_with_base_image() -> None:
    a = EnvironmentSpec(name="env", packages=dict(PINS))
    b = EnvironmentSpec(name="env", packages=dict(PINS), base_image="other:tag")
    assert a.lock_hash() != b.lock_hash()


def test_resolve_passes_when_all_pins_available() -> None:
    spec = EnvironmentSpec(name="env", packages=dict(PINS))
    mirror = FakeMirror({(n, v) for n, v in PINS.items()})
    assert spec.resolve(mirror) is True


def test_resolve_raises_listing_missing() -> None:
    spec = EnvironmentSpec(name="env", packages=dict(PINS))
    # Mirror has torch but not numpy.
    mirror = FakeMirror({("torch", "2.3.1")})
    with pytest.raises(UnresolvedEnvironment) as exc:
        spec.resolve(mirror)
    msg = str(exc.value)
    assert "numpy==1.26.4" in msg
    assert "torch" not in msg  # torch resolved, so it is not reported missing
