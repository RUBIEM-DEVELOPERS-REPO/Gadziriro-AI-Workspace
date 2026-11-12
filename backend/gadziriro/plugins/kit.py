"""Signed, sandboxed plug-in kit (FR-32, BRD section 24).

Plug-ins add model types (vision / speech / tabular). They are **signed**: a bundle is
the manifest, the payload and an Ed25519 signature over the canonical manifest, and the
manifest carries the payload's sha256. They are **sandboxed**: per section 24 a plug-in
runs only inside its own isolated sandbox (no network, no host filesystem, no host
secrets). This kit never executes a plug-in; it verifies, records the registration
(DISABLED by default) and exposes the :class:`SandboxSpec` a future runner honours.
Actual execution is out of scope for Phase 4.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import Enum
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from ..audit.base import AuditEvent, AuditSink
from ..core.canonical_json import canonical_bytes
from ..core.crypto import sha256_hex
from ..core.errors import GadziriroError, NotFound

_REQUIRED = ("name", "kind", "version", "entrypoint", "api_version")


class PluginError(GadziriroError):
    """A plug-in bundle is unsigned, tampered, or otherwise invalid."""


class PluginKind(str, Enum):
    """Model types a plug-in may add."""

    VISION = "vision"
    SPEECH = "speech"
    TABULAR = "tabular"


@dataclass(frozen=True)
class PluginManifest:
    """Verified plug-in metadata; ``sha256`` is the payload checksum."""

    name: str
    kind: PluginKind
    version: str
    entrypoint: str
    api_version: str
    sha256: str


@dataclass(frozen=True)
class SandboxSpec:
    """Isolation contract a plug-in must run under (section 24); never executed here."""

    isolated: bool = True
    network: bool = False
    host_filesystem: bool = False
    host_secrets: bool = False
    executed_by_kit: bool = False


@dataclass(frozen=True)
class PluginBundle:
    """A signed plug-in: manifest dict, payload bytes, base64 Ed25519 signature."""

    manifest: dict[str, Any]
    payload: bytes
    sig: str


@dataclass(frozen=True)
class PluginRecord:
    """A registered plug-in: verified manifest, enabled flag, sandbox descriptor."""

    manifest: PluginManifest
    enabled: bool
    sandbox: SandboxSpec


def sign_plugin(
    manifest_dict: dict[str, Any], payload: bytes, signing_key: SigningKey
) -> PluginBundle:
    """Sign a plug-in: stamp the payload sha256 into the manifest and sign it."""
    missing = [k for k in _REQUIRED if k not in manifest_dict]
    if missing:
        raise PluginError(f"manifest missing fields: {', '.join(missing)}")
    manifest = dict(manifest_dict)
    try:
        manifest["kind"] = PluginKind(manifest["kind"]).value
    except ValueError as exc:
        raise PluginError(f"unknown plug-in kind: {manifest['kind']}") from exc
    manifest["sha256"] = sha256_hex(payload)
    sig = signing_key.sign(canonical_bytes(manifest)).signature
    return PluginBundle(manifest, payload, base64.b64encode(sig).decode("ascii"))


def verify_plugin(
    bundle: PluginBundle,
    verify_key: VerifyKey | bytes,
    *,
    allowed_api_versions: frozenset[str] | None = None,
) -> PluginManifest:
    """Verify signature, checksum (and api_version if given); return the manifest."""
    if isinstance(verify_key, (bytes, bytearray)):
        verify_key = VerifyKey(bytes(verify_key))
    manifest = bundle.manifest
    if not isinstance(manifest, dict) or not bundle.sig:
        raise PluginError("plug-in is unsigned")
    try:
        verify_key.verify(canonical_bytes(manifest), base64.b64decode(bundle.sig))
    except (BadSignatureError, ValueError, TypeError) as exc:
        raise PluginError("plug-in signature verification failed") from exc
    if sha256_hex(bundle.payload) != manifest.get("sha256"):
        raise PluginError("plug-in payload checksum mismatch")
    if any(k not in manifest for k in _REQUIRED):
        raise PluginError("plug-in manifest incomplete")
    api = str(manifest["api_version"])
    if allowed_api_versions is not None and api not in allowed_api_versions:
        raise PluginError(f"unsupported plug-in api_version: {api}")
    try:
        kind = PluginKind(manifest["kind"])
    except ValueError as exc:
        raise PluginError(f"unknown plug-in kind: {manifest['kind']}") from exc
    return PluginManifest(
        name=str(manifest["name"]),
        kind=kind,
        version=str(manifest["version"]),
        entrypoint=str(manifest["entrypoint"]),
        api_version=api,
        sha256=str(manifest["sha256"]),
    )


class PluginRegistry:
    """Registry of verified plug-ins. Installs DISABLED; never executes anything."""

    def __init__(
        self,
        verify_key: VerifyKey | bytes,
        *,
        allowed_api_versions: frozenset[str] = frozenset({"1"}),
        audit: AuditSink | None = None,
    ) -> None:
        self._verify_key = verify_key
        self._allowed = allowed_api_versions
        self._audit = audit
        self._plugins: dict[str, PluginRecord] = {}

    def _log(self, action: str, name: str, **meta: Any) -> None:
        if self._audit is None:
            return
        self._audit.append(
            AuditEvent(
                actor="system",
                action=action,
                target=name,
                level="security",
                meta=meta,
            )
        )

    def install(self, bundle: PluginBundle) -> PluginManifest:
        """Verify (signature first) then register DISABLED; refuse otherwise."""
        try:
            manifest = verify_plugin(
                bundle, self._verify_key, allowed_api_versions=self._allowed
            )
        except PluginError as exc:
            self._log("plugin.install.refused", "", reason=str(exc))
            raise
        self._plugins[manifest.name] = PluginRecord(manifest, False, SandboxSpec())
        self._log(
            "plugin.install",
            manifest.name,
            version=manifest.version,
            kind=manifest.kind.value,
        )
        return manifest

    def get(self, name: str) -> PluginRecord:
        """Return a registered plug-in or raise NotFound."""
        try:
            return self._plugins[name]
        except KeyError:
            raise NotFound(f"plug-in not found: {name}") from None

    def _set(self, name: str, enabled: bool) -> PluginRecord:
        rec = self.get(name)
        new = PluginRecord(rec.manifest, enabled, rec.sandbox)
        self._plugins[name] = new
        self._log("plugin.enable" if enabled else "plugin.disable", name)
        return new

    def enable(self, name: str) -> PluginRecord:
        """Mark a registered plug-in enabled (it still runs only in its sandbox)."""
        return self._set(name, True)

    def disable(self, name: str) -> PluginRecord:
        """Mark a registered plug-in disabled."""
        return self._set(name, False)

    def list_plugins(self) -> list[PluginRecord]:
        """All registered plug-ins, sorted by name."""
        return [self._plugins[n] for n in sorted(self._plugins)]
