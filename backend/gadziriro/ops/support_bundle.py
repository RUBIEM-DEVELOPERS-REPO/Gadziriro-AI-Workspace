"""PII-stripped support bundles for troubleshooting (FR-40).

A *support bundle* is a small JSON snapshot an operator can hand to support to
diagnose a problem: a configuration summary, recent log/metrics excerpts, and
component versions. Because the workspace holds personal (PERSONAL) and health
(PHI) data, a support bundle must **never** carry personal data or raw dataset
bytes off the box.

Two layers enforce that:

* **Collection** skips anything under a dataset / ``personal`` / ``phi`` /
  ``subject`` path and never reads raw dataset blobs, so sensitive bytes are
  never gathered in the first place.
* **Redaction** runs an injectable redactor over everything that *is* gathered.
  The :func:`default_redactor` masks obvious PII (email addresses) and fully
  redacts values under sensitive keys (``email``, ``subject``, ``patient``,
  secrets, …). Callers can pass their own redactor to extend this.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from ..core.canonical_json import canonical_json
from ..core.objectstore import ObjectStore

__all__ = ["build_support_bundle", "default_redactor", "Redactor"]

# A redactor takes the gathered bundle and returns (redacted_bundle, count).
Redactor = Callable[[Any], "tuple[Any, int]"]

_BUNDLE_PREFIX = "support_bundles"

# Path segments whose contents are personal/sensitive and must never be read.
_SENSITIVE_SEGMENTS = frozenset({"datasets", "personal", "phi", "subjects"})

# Files we treat as readable log/metric excerpts (text, line-oriented).
_LOG_SUFFIXES = frozenset({".log", ".jsonl", ".ndjson"})

# Keys whose values are redacted wholesale (case-insensitive substring match).
# ``actor``/``target`` are included because log records put principal and subject
# identifiers there, and a support bundle must carry neither off the box.
_SENSITIVE_KEY_TOKENS = (
    "email",
    "subject",
    "patient",
    "phi",
    "personal",
    "ssn",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "actor",
    "target",
)

_MASK = "【REDACTED】"  # γ€ŽREDACTEDγ€
_EMAIL_MASK = "【REDACTED-EMAIL】"
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_MAX_LOG_LINES = 50


def _now_iso() -> str:
    """Return the current time as an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# redaction
# --------------------------------------------------------------------------- #
def _redact_string(value: str) -> tuple[str, int]:
    """Mask PII patterns (emails) inside a free-text string; return (masked, n)."""
    count = 0

    def _sub(_match: "re.Match[str]") -> str:
        nonlocal count
        count += 1
        return _EMAIL_MASK

    return _EMAIL_RE.sub(_sub, value), count


def _is_sensitive_key(key: Optional[str]) -> bool:
    """Return True if ``key`` names a field whose value should be fully redacted."""
    if not key:
        return False
    lowered = key.lower()
    return any(token in lowered for token in _SENSITIVE_KEY_TOKENS)


def _redact(obj: Any, key: Optional[str]) -> tuple[Any, int]:
    """Recursively redact ``obj`` (keyed by ``key`` for sensitive-key matching)."""
    if isinstance(obj, dict):
        out: dict[Any, Any] = {}
        total = 0
        for k, v in obj.items():
            red, n = _redact(v, str(k))
            out[k] = red
            total += n
        return out, total
    if isinstance(obj, (list, tuple)):
        out_list: list[Any] = []
        total = 0
        for item in obj:
            red, n = _redact(item, key)
            out_list.append(red)
            total += n
        return out_list, total
    if isinstance(obj, str):
        if _is_sensitive_key(key):
            return _MASK, 1
        return _redact_string(obj)
    return obj, 0


def default_redactor(bundle: Any) -> tuple[Any, int]:
    """Default PII redactor: mask emails and fully redact sensitive-key values.

    Returns the redacted copy and the number of fields/occurrences redacted.
    Injectable: pass a different callable with the same signature to
    :func:`build_support_bundle` to extend or replace this behaviour.
    """
    return _redact(bundle, None)


# --------------------------------------------------------------------------- #
# collection
# --------------------------------------------------------------------------- #
def _is_sensitive_path(rel: Path) -> bool:
    """Return True if any path segment is a sensitive/dataset segment."""
    for part in rel.parts:
        lowered = part.lower()
        if lowered in _SENSITIVE_SEGMENTS or "subject" in lowered:
            return True
    return False


def _config_summary(data_dir: Path) -> dict[str, Any]:
    """Summarise top-level JSON config files by key names only (never values)."""
    summary: dict[str, Any] = {}
    if not data_dir.is_dir():
        return summary
    for child in sorted(data_dir.glob("*.json")):
        if not child.is_file():
            continue
        try:
            doc = json.loads(child.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            summary[child.name] = {"keys": [], "note": "unreadable"}
            continue
        keys = sorted(doc.keys()) if isinstance(doc, dict) else []
        summary[child.name] = {"keys": keys}
    return summary


def _parse_line(line: str) -> Any:
    """Parse a log line as a JSON object when possible, else keep it as text.

    Structured records are returned as dicts so the key-based redactor can mask
    their sensitive fields (``actor``/``target``/``subjects``/…); anything else
    stays a string and is scrubbed for inline PII (emails).
    """
    try:
        parsed = json.loads(line)
    except ValueError:
        return line
    return parsed if isinstance(parsed, dict) else line


def _log_excerpts(data_dir: Path) -> dict[str, list[Any]]:
    """Collect the last lines of line-oriented log files, skipping sensitive paths."""
    excerpts: dict[str, list[Any]] = {}
    if not data_dir.is_dir():
        return excerpts
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _LOG_SUFFIXES:
            continue
        rel = path.relative_to(data_dir)
        if _is_sensitive_path(rel):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        excerpts[rel.as_posix()] = [_parse_line(ln) for ln in lines[-_MAX_LOG_LINES:]]
    return excerpts


def _versions() -> dict[str, str]:
    """Return component versions for the bundle."""
    try:
        from .. import __version__ as gadziriro_version
    except Exception:  # pragma: no cover - defensive
        gadziriro_version = "unknown"
    return {
        "python": sys.version.split()[0],
        "gadziriro": gadziriro_version,
    }


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def build_support_bundle(
    *,
    data_dir: Path,
    out_store: ObjectStore,
    redactor: Optional[Redactor] = None,
) -> dict[str, Any]:
    """Build a PII-stripped troubleshooting bundle and store it (FR-40).

    Gathers a config summary (key names only), recent log/metrics excerpts, and
    component versions from ``data_dir`` — deliberately skipping dataset blobs
    and any ``personal``/``phi``/``subject`` paths — then runs ``redactor`` over
    the result to mask any remaining PII. The redacted bundle is written to
    ``out_store`` under ``support_bundles/<ts>/bundle.json``.

    Args:
        data_dir: Workspace state directory to gather diagnostics from.
        out_store: Destination object store for the bundle.
        redactor: Optional redactor (defaults to :func:`default_redactor`).

    Returns:
        ``{"bundle_key", "redacted_fields_count", "created_at"}``.
    """
    redactor = redactor or default_redactor
    data_dir = Path(data_dir)
    created_at = _now_iso()

    raw_bundle: dict[str, Any] = {
        "created_at": created_at,
        "versions": _versions(),
        "config_summary": _config_summary(data_dir),
        "logs": _log_excerpts(data_dir),
    }

    redacted, redacted_count = redactor(raw_bundle)

    ts_safe = created_at.replace(":", "").replace(".", "")
    bundle_key = f"{_BUNDLE_PREFIX}/{ts_safe}/bundle.json"
    out_store.put(bundle_key, canonical_json(redacted).encode("utf-8"))

    return {
        "bundle_key": bundle_key,
        "redacted_fields_count": redacted_count,
        "created_at": created_at,
    }
