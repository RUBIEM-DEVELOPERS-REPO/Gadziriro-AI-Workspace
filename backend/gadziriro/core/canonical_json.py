"""Canonical JSON — the ONE place this is defined.

Every component that hashes or signs a record must serialise it the same way,
byte-for-byte, or the audit hash chain and (later) policy signatures break.
Atomic (the sibling pentest platform) learned this the hard way by duplicating
the function in three modules; we centralise it here.

Rules:
- keys sorted recursively
- no insignificant whitespace (compact separators)
- UTF-8, non-ASCII preserved (ensure_ascii=False) so byte output is stable
- NaN/Infinity rejected (not valid JSON, non-deterministic across tools)
"""

from __future__ import annotations

import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Return the canonical JSON string for ``obj``."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(obj: Any) -> bytes:
    """Return the canonical JSON encoding as UTF-8 bytes (what we hash/sign)."""
    return canonical_json(obj).encode("utf-8")
