"""Shared primitives: canonical JSON, config, logging, errors, crypto.

This package is the single source of truth for cross-cutting concerns. Service
packages (audit, auth, gateway, sessions, runtime, compute, policy, installer)
depend on `core`; `core` depends on nothing else in the project.
"""
