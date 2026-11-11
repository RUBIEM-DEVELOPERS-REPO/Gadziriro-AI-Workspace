"""Signed update packages (FR-30).

An update bundle is ``payload`` plus a manifest, with an Ed25519 signature over the
canonical manifest. Verification is fully offline (the verify key is shipped with the
install), so updates can be applied online or carried in to an air-gapped box. The
signature is the trust root — an unsigned or tampered bundle is refused.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from ..core.canonical_json import canonical_bytes, canonical_json
from ..core.crypto import sha256_hex
from ..core.errors import GadziriroError

_MAGIC = "GZUP1"
_SEP = b"\n--gadziriro-update--\n"


class UpdateError(GadziriroError):
    """An update bundle is unsigned, tampered, or otherwise invalid."""


@dataclass(frozen=True)
class UpdatePackage:
    version: str
    created_at: str
    artifact_sha256: str
    size: int
    notes: str = ""


def _manifest(version: str, payload: bytes, created_at: str, notes: str) -> dict:
    return {
        "magic": _MAGIC,
        "version": version,
        "created_at": created_at,
        "artifact_sha256": sha256_hex(payload),
        "size": len(payload),
        "notes": notes,
    }


def build_update(
    version: str,
    payload: bytes,
    signing_key: SigningKey,
    *,
    created_at: str = "1970-01-01T00:00:00Z",
    notes: str = "",
) -> tuple[bytes, dict]:
    """Build a signed update bundle; returns (bundle_bytes, manifest)."""
    manifest = _manifest(version, payload, created_at, notes)
    sig = signing_key.sign(canonical_bytes(manifest)).signature
    header = {
        "manifest": manifest,
        "sig": base64.b64encode(sig).decode("ascii"),
    }
    bundle = canonical_json(header).encode("utf-8") + _SEP + payload
    return bundle, manifest


def _split(bundle: bytes) -> tuple[dict, bytes]:
    try:
        head_raw, payload = bundle.split(_SEP, 1)
    except ValueError as exc:
        raise UpdateError("malformed update bundle (no separator)") from exc
    import json

    try:
        header = json.loads(head_raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise UpdateError("malformed update header") from exc
    return header, payload


def verify_update(bundle: bytes, verify_key: VerifyKey | bytes) -> UpdatePackage:
    """Verify signature + checksum; return the UpdatePackage or raise UpdateError."""
    if isinstance(verify_key, (bytes, bytearray)):
        verify_key = VerifyKey(bytes(verify_key))
    header, payload = _split(bundle)
    manifest = header.get("manifest")
    sig_b64 = header.get("sig")
    if not isinstance(manifest, dict) or not isinstance(sig_b64, str):
        raise UpdateError("update header missing manifest or signature")
    try:
        verify_key.verify(canonical_bytes(manifest), base64.b64decode(sig_b64))
    except (BadSignatureError, ValueError) as exc:
        raise UpdateError("update signature verification failed") from exc
    if sha256_hex(payload) != manifest.get("artifact_sha256"):
        raise UpdateError("update payload checksum mismatch")
    return UpdatePackage(
        version=str(manifest["version"]),
        created_at=str(manifest.get("created_at", "")),
        artifact_sha256=str(manifest["artifact_sha256"]),
        size=int(manifest.get("size", len(payload))),
        notes=str(manifest.get("notes", "")),
    )
