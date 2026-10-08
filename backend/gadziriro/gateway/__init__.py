"""Gateway: the single front door (SSO/MFA later, local accounts now).

Handles RBAC, rate limiting and audit. `registry.py` is the extension point: each
service package exposes an APIRouter and registers it, so the app wires itself
without the gateway importing every service.
"""
