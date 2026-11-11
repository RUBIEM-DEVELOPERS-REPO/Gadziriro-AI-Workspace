"""Unit tests for applying / rolling back updates."""

from __future__ import annotations

import pytest
from nacl.signing import SigningKey

from gadziriro.updates.apply import UpdateManager
from gadziriro.updates.signing import UpdateError, build_update


def _mgr(current="1.0.0"):
    sk = SigningKey.generate()
    return UpdateManager(verify_key=sk.verify_key, current_version=current), sk


def test_apply_bumps_version() -> None:
    mgr, sk = _mgr("1.0.0")
    bundle, _ = build_update("1.1.0", b"p", sk)
    assert mgr.apply_update(bundle) == "1.1.0"
    assert mgr.current_version == "1.1.0"


def test_unsigned_bundle_refused() -> None:
    mgr, _ = _mgr()
    with pytest.raises(UpdateError):
        mgr.apply_update(b"garbage")


def test_downgrade_refused_unless_forced() -> None:
    mgr, sk = _mgr("2.0.0")
    bundle, _ = build_update("1.0.0", b"p", sk)
    with pytest.raises(UpdateError):
        mgr.apply_update(bundle)
    assert mgr.apply_update(bundle, force=True) == "1.0.0"


def test_rollback_returns_previous() -> None:
    mgr, sk = _mgr("1.0.0")
    mgr.apply_update(build_update("1.1.0", b"p", sk)[0])
    assert mgr.rollback() == "1.0.0"
    with pytest.raises(UpdateError):
        mgr.rollback()  # nothing left to roll back to


def test_offline_bundle_from_bytes() -> None:
    mgr, sk = _mgr("1.0.0")
    bundle, _ = build_update("1.2.0", b"p", sk)
    assert mgr.import_offline_bundle(bundle) == "1.2.0"
