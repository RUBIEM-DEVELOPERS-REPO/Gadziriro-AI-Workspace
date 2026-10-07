"""Tamper-evident audit log (FR-19, NFR-04).

Append-only, hash-chained JSONL. Any edit, deletion, or reordering of a past
record breaks the chain and is caught by `verify()`. The concrete implementation
lives in `log.py`; `base.py` is the contract other packages type against.
"""

from .base import AuditEvent, AuditSink, VerifyResult

__all__ = ["AuditEvent", "AuditSink", "VerifyResult"]
