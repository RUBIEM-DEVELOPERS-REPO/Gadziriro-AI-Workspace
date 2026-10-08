"""Unit tests for the default-deny egress policy (FR-20, NFR-05)."""

from __future__ import annotations

import pytest

from gadziriro.core.errors import PolicyDenied
from gadziriro.policy.egress import EgressPolicy


def _fake_resolver(mapping: dict[str, list[str]]):
    """Build a getaddrinfo-compatible resolver from host -> [ip, ...]."""

    def resolve(host, *_args, **_kwargs):
        ips = mapping.get(host, [])
        if not ips:
            import socket

            raise socket.gaierror(f"no fake record for {host}")
        return [(2, 1, 6, "", (ip, 0)) for ip in ips]

    return resolve


def test_default_policy_denies_everything() -> None:
    policy = EgressPolicy()  # enabled_egress defaults to False
    assert policy.is_allowed("example.com") is False
    assert policy.is_allowed("8.8.8.8") is False
    with pytest.raises(PolicyDenied):
        policy.check("example.com")


def test_disabled_overrides_allow_rules() -> None:
    policy = EgressPolicy(allow_rules=["example.com"], enabled_egress=False)
    assert policy.is_allowed("example.com") is False


def test_enabled_allows_only_matching_targets() -> None:
    policy = EgressPolicy(allow_rules=["example.com"], enabled_egress=True)
    assert policy.is_allowed("example.com") is True
    assert policy.is_allowed("api.example.com") is True  # suffix match
    assert policy.is_allowed("evil.com") is False
    policy.check("example.com")  # must not raise
    with pytest.raises(PolicyDenied) as exc:
        policy.check("evil.com")
    assert "evil.com" in exc.value.reason


def test_cidr_membership() -> None:
    policy = EgressPolicy(allow_rules=["10.0.0.0/8"], enabled_egress=True)
    assert policy.is_allowed("10.1.2.3") is True
    assert policy.is_allowed("11.0.0.1") is False


def test_deny_overrides_allow() -> None:
    policy = EgressPolicy(
        allow_rules=["10.0.0.0/8"],
        deny_rules=["10.0.0.5"],
        enabled_egress=True,
    )
    assert policy.is_allowed("10.0.0.4") is True
    assert policy.is_allowed("10.0.0.5") is False
    # host-level deny also wins over a host allow
    hostpol = EgressPolicy(
        allow_rules=["example.com"],
        deny_rules=["bad.example.com"],
        enabled_egress=True,
    )
    assert hostpol.is_allowed("bad.example.com") is False


def test_resolve_and_check_blocks_rebinding() -> None:
    # Allowed name + CIDR scope, but the name resolves to an out-of-scope IP.
    policy = EgressPolicy(
        allow_rules=["svc.internal", "10.0.0.0/8"],
        enabled_egress=True,
    )
    resolver = _fake_resolver({"svc.internal": ["203.0.113.9"]})  # out of scope
    assert policy.resolve_and_check("svc.internal", resolver=resolver) is False


def test_resolve_and_check_allows_in_scope() -> None:
    policy = EgressPolicy(
        allow_rules=["svc.internal", "10.0.0.0/8"],
        enabled_egress=True,
    )
    resolver = _fake_resolver({"svc.internal": ["10.0.0.7", "10.0.0.8"]})
    assert policy.resolve_and_check("svc.internal", resolver=resolver) is True


def test_resolve_and_check_denied_when_any_ip_excluded() -> None:
    policy = EgressPolicy(
        allow_rules=["svc.internal", "10.0.0.0/8"],
        deny_rules=["10.0.0.8"],
        enabled_egress=True,
    )
    # One good IP, one explicitly denied IP -> whole name rejected.
    resolver = _fake_resolver({"svc.internal": ["10.0.0.7", "10.0.0.8"]})
    assert policy.resolve_and_check("svc.internal", resolver=resolver) is False


def test_resolve_and_check_zero_egress_when_disabled() -> None:
    policy = EgressPolicy(allow_rules=["svc.internal"], enabled_egress=False)
    resolver = _fake_resolver({"svc.internal": ["10.0.0.7"]})
    assert policy.resolve_and_check("svc.internal", resolver=resolver) is False
