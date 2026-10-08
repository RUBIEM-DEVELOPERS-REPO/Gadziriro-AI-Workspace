"""Hashing helpers used by the audit chain (and later, signed policy docs)."""

from __future__ import annotations

import hashlib
from typing import Any

from .canonical_json import canonical_bytes

GENESIS = "GENESIS"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_record(record: dict[str, Any]) -> str:
    """SHA-256 of the canonical encoding of a record.

    Callers must strip any self-referential ``hash`` field before calling, so the
    hash covers everything *except* itself.
    """
    return sha256_hex(canonical_bytes(record))
