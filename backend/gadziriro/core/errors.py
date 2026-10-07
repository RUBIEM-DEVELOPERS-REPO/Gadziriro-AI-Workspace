"""Project-wide exception hierarchy.

Keeping these in `core` lets the gateway translate them to HTTP responses in one
place without importing every service package.
"""

from __future__ import annotations


class GadziriroError(Exception):
    """Base class for all expected (handled) errors."""


class ConfigError(GadziriroError):
    """Invalid or missing configuration."""


class AuthError(GadziriroError):
    """Authentication or authorization failure."""


class PolicyDenied(GadziriroError):
    """An action was blocked by the policy engine (e.g. egress denied)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class RuntimeAdapterError(GadziriroError):
    """The runtime adapter could not satisfy a request (GPU, kernel, job)."""


class AuditError(GadziriroError):
    """The audit log is unreadable, corrupt, or failed to append."""


class NotFound(GadziriroError):
    """A requested resource does not exist."""
