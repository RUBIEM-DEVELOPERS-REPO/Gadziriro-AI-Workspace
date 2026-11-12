"""Software Bill of Materials generator (NFR-18).

Parses ``backend/requirements.txt`` into a minimal, offline SBOM (no network).

Shape::

    {
      "bomFormat": "gadziriro-sbom",
      "specVersion": "1.0",
      "generated_at": "<ISO-8601 UTC>",
      "source": "<requirements file name>",
      "component_count": <int>,
      "components": [{"name": str, "version_spec": str, "extras": [str]}, ...]
    }
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..core.objectstore import ObjectStore

SBOM_KEY = "sbom/sbom.json"
_DEFAULT_REQUIREMENTS = Path(__file__).resolve().parents[2] / "requirements.txt"
_REQ_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?\s*(.*)$")


def _parse_line(line: str) -> Optional[dict[str, Any]]:
    """Parse one requirement line; return None for blanks/comments/options."""
    text = line.split(" #", 1)[0].strip()
    if not text or text.startswith(("#", "-")):
        return None
    text = text.split(";", 1)[0].strip()  # drop environment markers
    match = _REQ_RE.match(text)
    if not match:
        return None
    name, extras, spec = match.groups()
    return {
        "name": name.lower(),
        "version_spec": spec.strip(),
        "extras": sorted(e.strip() for e in (extras or "").split(",") if e.strip()),
    }


def build_sbom(requirements_path: Optional[Path | str] = None) -> dict[str, Any]:
    """Build an SBOM dict from a requirements file (default: backend's)."""
    path = Path(requirements_path) if requirements_path else _DEFAULT_REQUIREMENTS
    components: list[dict[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = _parse_line(line)
            if entry is not None:
                components.append(entry)
    return {
        "bomFormat": "gadziriro-sbom",
        "specVersion": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": path.name,
        "component_count": len(components),
        "components": components,
    }


def write_sbom(sbom: dict[str, Any], out_store: ObjectStore) -> str:
    """Store ``sbom`` under ``sbom/sbom.json``; return the key."""
    out_store.put(SBOM_KEY, json.dumps(sbom, indent=2, sort_keys=True).encode("utf-8"))
    return SBOM_KEY
