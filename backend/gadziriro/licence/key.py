"""Offline licence-key validation (FR-31).

A licence key is a signed, self-contained token: the workspace can verify it
WITHOUT any network call -- there is no licence server to phone (NFR-02). The
scheme is Ed25519 (PyNaCl): the vendor signs a canonical-JSON payload with a
private signing key; the install embeds only the public verifying key and checks
the signature plus the expiry date locally.

Token wire format (JWT-like, two base64url parts, no padding)::

    <base64url(canonical_json(payload))>.<base64url(signature)>

Everything here is stdlib + PyNaCl and fully offline; ``now`` is injectable so
tests can simulate an expired key deterministically.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import date, datetime

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from ..core.canonical_json import canonical_bytes
from ..core.errors import GadziriroError


class LicenceError(GadziriroError):
    """A licence token is malformed, tampered with, or expired."""


@dataclass(frozen=True)
class LicenceInfo:
    """The validated contents of a licence key."""

    customer: str
    expiry: str  # ISO-8601 date, e.g. "2027-01-31"
    features: tuple[str, ...] = ()
    seats: int = 1


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + pad)
    except (ValueError, TypeError) as exc:  # pragma: no cover - defensive
        raise LicenceError("malformed licence token: bad base64") from exc


def _payload(info: LicenceInfo) -> dict[str, object]:
    return {
        "customer": info.customer,
        "expiry": info.expiry,
        "features": list(info.features),
        "seats": info.seats,
    }


def issue_licence(info: LicenceInfo, signing_key: SigningKey) -> str:
    """Mint a signed licence token for ``info`` (vendor-side helper).

    Parameters
    ----------
    info:
        The licence contents to embed.
    signing_key:
        The vendor's Ed25519 private key.

    Returns
    -------
    str
        A ``payload.signature`` token consumable by :func:`validate_licence`.
    """
    payload_bytes = canonical_bytes(_payload(info))
    signature = signing_key.sign(payload_bytes).signature
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


def _as_date(value: date | datetime | None) -> date:
    if value is None:
        return datetime.utcnow().date()
    if isinstance(value, datetime):
        return value.date()
    return value


def validate_licence(
    token: str,
    verify_key: VerifyKey | bytes,
    *,
    now: date | datetime | None = None,
) -> LicenceInfo:
    """Verify ``token`` offline and return its :class:`LicenceInfo`.

    Raises :class:`LicenceError` if the token is malformed, the signature does
    not verify (tampered), or the licence has expired.

    Parameters
    ----------
    token:
        A token produced by :func:`issue_licence`.
    verify_key:
        The vendor's Ed25519 public key (``VerifyKey`` or 32 raw bytes).
    now:
        Reference date for the expiry check; defaults to today (UTC).
    """
    vk = verify_key if isinstance(verify_key, VerifyKey) else VerifyKey(verify_key)

    try:
        payload_part, sig_part = token.split(".")
    except ValueError as exc:
        raise LicenceError("malformed licence token: expected two parts") from exc

    payload_bytes = _b64url_decode(payload_part)
    signature = _b64url_decode(sig_part)

    try:
        vk.verify(payload_bytes, signature)
    except BadSignatureError as exc:
        raise LicenceError("licence signature verification failed (tampered)") from exc

    try:
        data = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise LicenceError("malformed licence payload: bad JSON") from exc

    try:
        info = LicenceInfo(
            customer=str(data["customer"]),
            expiry=str(data["expiry"]),
            features=tuple(data.get("features", ())),
            seats=int(data.get("seats", 1)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LicenceError("malformed licence payload: missing fields") from exc

    try:
        expiry_date = date.fromisoformat(info.expiry)
    except ValueError as exc:
        raise LicenceError(f"malformed licence expiry: {info.expiry!r}") from exc

    if _as_date(now) > expiry_date:
        raise LicenceError(f"licence expired on {info.expiry}")

    return info
