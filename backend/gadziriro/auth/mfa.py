"""Time-based one-time password (TOTP) second factor (FR-17).

A from-scratch RFC 6238 / RFC 4226 implementation using only the standard
library (:mod:`hmac`, :mod:`struct`, :mod:`base64`, :mod:`hashlib`,
:mod:`secrets`) — no third-party OTP dependency. TOTP is HOTP with the counter
derived from the current Unix time divided by a step (default 30s).

The verifier accepts codes within +/- ``window`` steps to tolerate clock skew
between the server and the authenticator app.

.. note::
   Auto-logout (FR-17) is **not** implemented here: it is enforced by the
   gateway's short-lived JWT expiry, which is already present. This module only
   provides the *second factor* (the TOTP code generation and verification);
   session lifetime remains the gateway's responsibility.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode


def generate_secret(num_bytes: int = 20) -> str:
    """Return a fresh base32-encoded TOTP secret.

    :param num_bytes: entropy in bytes (RFC 4226 recommends >= 20 for SHA-1).
    :returns: an un-padded upper-case base32 string suitable for ``otpauth://``.
    """
    raw = secrets.token_bytes(num_bytes)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    """Decode a (possibly un-padded, spaced, lower-case) base32 secret."""
    cleaned = secret.strip().replace(" ", "").upper()
    padding = (-len(cleaned)) % 8
    return base64.b32decode(cleaned + ("=" * padding))


def _hotp(key: bytes, counter: int, *, digits: int) -> str:
    """RFC 4226 HOTP: HMAC-SHA1 of the counter, with dynamic truncation."""
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10**digits)).zfill(digits)


def totp(
    secret: str,
    *,
    for_time: float | None = None,
    step: int = 30,
    digits: int = 6,
) -> str:
    """Compute the TOTP code for ``secret`` at ``for_time`` (RFC 6238).

    :param secret: the base32-encoded shared secret.
    :param for_time: Unix timestamp to compute for; defaults to ``time.time()``.
    :param step: time step in seconds (default 30).
    :param digits: number of output digits (default 6).
    """
    now = time.time() if for_time is None else for_time
    counter = int(now // step)
    return _hotp(_decode_secret(secret), counter, digits=digits)


def verify(
    secret: str,
    code: str,
    *,
    for_time: float | None = None,
    step: int = 30,
    digits: int = 6,
    window: int = 1,
) -> bool:
    """Verify a TOTP ``code`` against ``secret`` within a skew ``window``.

    Accepts codes from ``window`` steps in the past through ``window`` steps in
    the future (inclusive) to tolerate clock drift. Comparison is constant-time.

    :param window: number of steps of tolerance on each side (default 1).
    :returns: ``True`` if ``code`` matches any step in the window.
    """
    if not code or not code.isdigit():
        return False
    now = time.time() if for_time is None else for_time
    key = _decode_secret(secret)
    base = int(now // step)
    candidate = code.zfill(digits)
    for drift in range(-window, window + 1):
        expected = _hotp(key, base + drift, digits=digits)
        if hmac.compare_digest(expected, candidate):
            return True
    return False


def provisioning_uri(secret: str, account: str, issuer: str = "Gadziriro") -> str:
    """Build an ``otpauth://`` provisioning URI (for QR enrolment).

    :param secret: the base32-encoded shared secret.
    :param account: the account name (usually the username or email).
    :param issuer: the issuer label shown by the authenticator app.
    """
    label = f"{issuer}:{account}"
    params = {
        "secret": secret,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": "6",
        "period": "30",
    }
    return f"otpauth://totp/{quote(label)}?{urlencode(params)}"
