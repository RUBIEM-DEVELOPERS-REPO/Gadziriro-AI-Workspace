"""FR-30 acceptance: signed updates online + offline, with one-step rollback."""

from __future__ import annotations

import pytest
from nacl.signing import SigningKey

from gadziriro.audit.log import AuditLog
from gadziriro.updates.apply import UpdateManager
from gadziriro.updates.signing import UpdateError, build_update


def test_signed_update_online_offline_and_rollback(tmp_path) -> None:
    sk = SigningKey.generate()
    audit = AuditLog(tmp_path / "audit.jsonl")
    mgr = UpdateManager(verify_key=sk.verify_key, current_version="1.0.0", audit=audit)

    # Online apply of a signed update.
    mgr.apply_update(build_update("1.1.0", b"release-1.1", sk)[0])
    assert mgr.current_version == "1.1.0"

    # Offline (air-gapped) bundle import, also signed.
    bundle = build_update("1.2.0", b"release-1.2", sk)[0]
    (tmp_path / "update.gzup").write_bytes(bundle)
    mgr.import_offline_bundle(tmp_path / "update.gzup")
    assert mgr.current_version == "1.2.0"

    # One-step rollback.
    assert mgr.rollback() == "1.1.0"

    # An unsigned bundle is refused outright.
    with pytest.raises(UpdateError):
        mgr.apply_update(b"unsigned")

    # Every applied change was audited and the chain still verifies.
    assert audit.verify().ok
