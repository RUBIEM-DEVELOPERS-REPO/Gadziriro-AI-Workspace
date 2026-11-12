"""Unit tests for the signed plug-in kit (FR-32)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from nacl.signing import SigningKey

from gadziriro.core.errors import NotFound
from gadziriro.plugins import (
    PluginBundle,
    PluginError,
    PluginKind,
    PluginRegistry,
    sign_plugin,
    verify_plugin,
)

KEY = SigningKey.generate()
PAYLOAD = b"plugin-bytes"


def _manifest(**over: object) -> dict:
    base = {
        "name": "vis",
        "kind": "vision",
        "version": "1.0.0",
        "entrypoint": "main:run",
        "api_version": "1",
    }
    base.update(over)
    return base


class _Sink:
    def __init__(self) -> None:
        self.events: list = []

    def append(self, event):  # noqa: ANN001
        self.events.append(event)
        return {}

    def verify(self):  # pragma: no cover
        raise NotImplementedError


def test_round_trip() -> None:
    m = verify_plugin(sign_plugin(_manifest(), PAYLOAD, KEY), KEY.verify_key)
    assert m.kind is PluginKind.VISION and m.name == "vis"


def test_tampered_payload_and_manifest() -> None:
    b = sign_plugin(_manifest(), PAYLOAD, KEY)
    with pytest.raises(PluginError):
        verify_plugin(replace(b, payload=b"evil"), KEY.verify_key)
    with pytest.raises(PluginError):
        verify_plugin(
            replace(b, manifest={**b.manifest, "entrypoint": "x"}), KEY.verify_key
        )


def test_wrong_key() -> None:
    b = sign_plugin(_manifest(), PAYLOAD, KEY)
    with pytest.raises(PluginError):
        verify_plugin(b, SigningKey.generate().verify_key)


def test_install_disabled_toggle_and_notfound() -> None:
    reg = PluginRegistry(KEY.verify_key)
    reg.install(sign_plugin(_manifest(), PAYLOAD, KEY))
    assert reg.get("vis").enabled is False
    assert reg.get("vis").sandbox.isolated and not reg.get("vis").sandbox.network
    assert reg.enable("vis").enabled is True
    assert reg.disable("vis").enabled is False
    assert [r.manifest.name for r in reg.list_plugins()] == ["vis"]
    with pytest.raises(NotFound):
        reg.get("nope")
    with pytest.raises(NotFound):
        reg.enable("nope")


def test_unsigned_refused_nothing_registered() -> None:
    reg = PluginRegistry(KEY.verify_key)
    good = sign_plugin(_manifest(), PAYLOAD, KEY)
    with pytest.raises(PluginError):
        reg.install(PluginBundle(good.manifest, PAYLOAD, ""))
    assert reg.list_plugins() == []


def test_disallowed_api_version() -> None:
    reg = PluginRegistry(KEY.verify_key)
    with pytest.raises(PluginError):
        reg.install(sign_plugin(_manifest(api_version="9"), PAYLOAD, KEY))
    assert reg.list_plugins() == []


def test_audit_events() -> None:
    sink = _Sink()
    reg = PluginRegistry(KEY.verify_key, audit=sink)
    reg.install(sign_plugin(_manifest(), PAYLOAD, KEY))
    reg.enable("vis")
    reg.disable("vis")
    assert [e.action for e in sink.events] == [
        "plugin.install",
        "plugin.enable",
        "plugin.disable",
    ]
