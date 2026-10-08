"""Default-deny egress policy matcher and gate (FR-20, NFR-05).

Conceptually ported from Atomic's net-scope engine:

* Egress is denied by default. With egress globally disabled (the privacy
  default derived from ``Settings.allow_egress == False``) NOTHING is ever
  allowed — zero egress.
* When egress is enabled, a target is allowed only if it matches an explicit
  allow-rule AND matches no deny-rule / exclusion. Deny always wins.
* Hostnames are re-resolved and every resolved IP is re-checked, so an allowed
  name that resolves to an out-of-scope / denied IP is rejected
  (anti-DNS-rebinding).

Rules are hosts (``api.internal``, suffix-matched), exact IPs
(``10.0.0.5``), or CIDRs (``10.0.0.0/8``).
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Callable, Optional

from gadziriro.core.errors import PolicyDenied

# A resolver maps a hostname to an iterable of getaddrinfo-style 5-tuples. We
# inject it so tests can supply a fake and never touch real DNS.
Resolver = Callable[[str], list[tuple]]


def _parse_network(rule: str) -> Optional[ipaddress._BaseNetwork]:
    """Parse a rule as an IP or CIDR network, or return ``None`` for a host.

    A bare IP (``10.0.0.5``) becomes a /32 (or /128) network so membership
    tests work uniformly with CIDRs.
    """
    try:
        return ipaddress.ip_network(rule, strict=False)
    except ValueError:
        return None


def _as_ip(target: str) -> Optional[ipaddress._BaseAddress]:
    """Return the parsed IP address of ``target``, or ``None`` if it is a host."""
    try:
        return ipaddress.ip_address(target)
    except ValueError:
        return None


def _host_matches(target: str, rule: str) -> bool:
    """Exact or suffix hostname match (case-insensitive).

    ``example.com`` matches ``example.com`` and ``api.example.com`` but not
    ``notexample.com``.
    """
    t = target.lower().rstrip(".")
    r = rule.lower().rstrip(".")
    return t == r or t.endswith("." + r)


class EgressPolicy:
    """Default-deny egress matcher and gate.

    Args:
        allow_rules: Hosts, IPs, or CIDRs that MAY be reached (when enabled).
        deny_rules: Hosts, IPs, or CIDRs that are always blocked. Deny wins.
        enabled_egress: Master switch. When ``False`` nothing is ever allowed.
    """

    def __init__(
        self,
        allow_rules: Optional[list[str]] = None,
        deny_rules: Optional[list[str]] = None,
        enabled_egress: bool = False,
    ) -> None:
        self.allow_rules: list[str] = list(allow_rules or [])
        self.deny_rules: list[str] = list(deny_rules or [])
        self.enabled_egress = enabled_egress

        self._allow_nets = [
            n for n in (_parse_network(r) for r in self.allow_rules) if n is not None
        ]
        self._deny_nets = [
            n for n in (_parse_network(r) for r in self.deny_rules) if n is not None
        ]
        self._allow_hosts = [r for r in self.allow_rules if _parse_network(r) is None]
        self._deny_hosts = [r for r in self.deny_rules if _parse_network(r) is None]

    # -- internal matchers ------------------------------------------------

    def _matches_any_net(
        self, ip: ipaddress._BaseAddress, nets: list[ipaddress._BaseNetwork]
    ) -> bool:
        return any(ip.version == n.version and ip in n for n in nets)

    def _is_denied(self, target: str) -> bool:
        """Does ``target`` match any deny rule?"""
        ip = _as_ip(target)
        if ip is not None:
            if self._matches_any_net(ip, self._deny_nets):
                return True
        else:
            if any(_host_matches(target, h) for h in self._deny_hosts):
                return True
        return False

    def _is_explicitly_allowed(self, target: str) -> bool:
        """Does ``target`` match any allow rule?"""
        ip = _as_ip(target)
        if ip is not None:
            return self._matches_any_net(ip, self._allow_nets)
        return any(_host_matches(target, h) for h in self._allow_hosts)

    # -- public API -------------------------------------------------------

    def is_allowed(self, target: str) -> bool:
        """Return whether ``target`` (a host, IP, or CIDR) may be reached.

        Zero-egress when disabled. Otherwise: allowed iff it matches an allow
        rule and matches no deny rule (deny always wins).
        """
        if not self.enabled_egress:
            return False
        if self._is_denied(target):
            return False
        return self._is_explicitly_allowed(target)

    def resolve_and_check(self, host: str, resolver: Optional[Resolver] = None) -> bool:
        """Resolve ``host`` and verify EVERY resolved IP is in scope.

        Anti-rebinding: the hostname itself must be allowed AND each IP it
        resolves to must not be denied/out-of-scope. If any resolved IP is
        denied, the whole check fails. The resolver is injectable (defaults to
        :func:`socket.getaddrinfo`) so tests never perform real DNS.
        """
        if not self.enabled_egress:
            return False

        # The name must itself clear the host-level allow/deny rules.
        if not self.is_allowed(host):
            return False

        resolve = resolver if resolver is not None else socket.getaddrinfo
        try:
            infos = resolve(host, None)
        except socket.gaierror:
            return False

        ips: list[str] = []
        for info in infos:
            # getaddrinfo tuple: (family, type, proto, canonname, sockaddr)
            sockaddr = info[4]
            ips.append(sockaddr[0])

        if not ips:
            return False

        for ip in ips:
            # A denied IP anywhere in the result set poisons the whole name.
            if self._is_denied(ip):
                return False
            # Each IP must also be positively in scope (allow rules may name IPs
            # or CIDRs). If only a host allow-rule exists, resolved IPs are not
            # independently allow-listed, so require explicit IP scope here.
            if not self._is_explicitly_allowed(ip):
                return False

        return True

    def check(self, target: str, actor: str = "user") -> None:
        """Gate an outbound attempt; raise :class:`PolicyDenied` if blocked.

        This is the single chokepoint the runtime/gateway calls before any
        outbound connection.
        """
        if not self.is_allowed(target):
            raise PolicyDenied(
                f"egress denied for actor={actor!r} target={target!r} "
                f"(enabled_egress={self.enabled_egress})"
            )
