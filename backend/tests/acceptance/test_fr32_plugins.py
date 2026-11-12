"""FR-32 acceptance: plug-ins are signed and sandboxed."""

from __future__ import annotations

from dataclasses import replace

import pytest
from nacl.signing import SigningKey

from gadziriro.plugins import PluginError, PluginKind, PluginRegistry, sign_plugin

KEY = SigningKey.generate()


@pytest.mark.parametrize("kind", list(PluginKind))
def test_signed_plugin_installs_verifies_enables(kind: PluginKind) -> None:
    reg = PluginRegistry(KEY.verify_key)
    bundle = sign_plugin(
        {
            "name": f"p-{kind.value}",
            "kind": kind.value,
            "version": "1.0",
            "entrypoint": "m:f",
            "api_version": "1",
        },
        b"payload",
        KEY,
    )
    assert reg.install(bundle).kind is kind
    assert reg.get(f"p-{kind.value}").enabled is False
    rec = reg.enable(f"p-{kind.value}")
    assert rec.enabled and rec.sandbox.isolated and not rec.sandbox.network
    assert not rec.sandbox.executed_by_kit


def test_unsigned_or_tampered_rejected() -> None:
    reg = PluginRegistry(KEY.verify_key)
    good = sign_plugin(
        {
            "name": "x",
            "kind": "speech",
            "version": "1",
            "entrypoint": "m:f",
            "api_version": "1",
        },
        b"ok",
        KEY,
    )
    for bad in (replace(good, sig=""), replace(good, payload=b"evil")):
        with pytest.raises(PluginError):
            reg.install(bad)
    assert reg.list_plugins() == []
