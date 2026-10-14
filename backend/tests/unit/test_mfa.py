"""Unit tests for the stdlib TOTP second factor (FR-17)."""

from __future__ import annotations

from gadziriro.auth import mfa

# A fixed base32 secret (RFC-style) so codes are deterministic for a fixed time.
SECRET = "JBSWY3DPEHPK3PXP"


def test_generate_secret_is_decodable_base32() -> None:
    secret = mfa.generate_secret()
    # Non-empty and usable: computing a code must not raise.
    assert secret
    assert mfa.totp(secret, for_time=0).isdigit()


def test_totp_is_stable_for_a_fixed_time() -> None:
    code_a = mfa.totp(SECRET, for_time=1_000_000_000)
    code_b = mfa.totp(SECRET, for_time=1_000_000_000)
    assert code_a == code_b
    assert len(code_a) == 6
    assert code_a.isdigit()


def test_totp_changes_across_steps() -> None:
    t = 1_000_000_000
    assert mfa.totp(SECRET, for_time=t) != mfa.totp(SECRET, for_time=t + 30)


def test_verify_accepts_current_code() -> None:
    t = 1_234_567_890
    code = mfa.totp(SECRET, for_time=t)
    assert mfa.verify(SECRET, code, for_time=t) is True


def test_verify_accepts_code_within_window() -> None:
    t = 1_234_567_890
    # Code generated one step in the past, verified now, window=1 -> accepted.
    prev_code = mfa.totp(SECRET, for_time=t - 30)
    assert mfa.verify(SECRET, prev_code, for_time=t, window=1) is True
    next_code = mfa.totp(SECRET, for_time=t + 30)
    assert mfa.verify(SECRET, next_code, for_time=t, window=1) is True


def test_verify_rejects_code_outside_window() -> None:
    t = 1_234_567_890
    far_code = mfa.totp(SECRET, for_time=t - 90)
    assert mfa.verify(SECRET, far_code, for_time=t, window=1) is False


def test_verify_rejects_wrong_code() -> None:
    t = 1_234_567_890
    assert mfa.verify(SECRET, "000000", for_time=t) is False
    assert mfa.verify(SECRET, "notadigit", for_time=t) is False
    assert mfa.verify(SECRET, "", for_time=t) is False


def test_provisioning_uri_shape() -> None:
    uri = mfa.provisioning_uri(SECRET, "alice@example.com", issuer="Gadziriro")
    assert uri.startswith("otpauth://totp/")
    assert "secret=" + SECRET in uri
    assert "issuer=Gadziriro" in uri
