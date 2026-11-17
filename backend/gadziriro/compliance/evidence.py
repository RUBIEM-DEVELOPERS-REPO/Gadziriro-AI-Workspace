"""Auditor evidence pack export (FR-26).

Bundles the privacy/compliance evidence the product already produces (audit
chain integrity, active policy packs, egress report, ROPA, backups, SBOM) into
one canonical-JSON pack plus a readable markdown summary.

BRD §9: the pack *supports* compliance efforts; it is not a certification and
all compliance claims require legal review.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from ..core.canonical_json import canonical_json
from ..ops.sbom import build_sbom
from ..policy.packs import merge_packs
from ..reporting.egress_report import build_egress_report
from .ropa import build_ropa

LEGAL_NOTE = (
    "BRD §9: this pack supports compliance efforts; it is not a certification. "
    "Any compliance claim requires legal review."
)
SECTIONS = ["audit", "policy", "egress", "ropa", "backups", "sbom"]


def _plain(obj: Any) -> Any:
    """Convert dataclasses/enums/sets into JSON-safe plain values."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return _plain(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted((_plain(v) for v in obj), key=str)
    if hasattr(obj, "value") and not isinstance(obj, (str, int, float, bool)):
        return _plain(obj.value)
    return obj


def _render_md(pack: dict[str, Any]) -> str:
    audit, egress = pack["audit"], pack["egress"]
    lines = [
        "# Auditor Evidence Pack",
        "",
        f"Generated: {pack['generated_at']}",
        "",
        f"> {pack['note']}",
        "",
        "## Audit chain integrity",
        f"- Intact: {audit['ok']}",
        f"- Records verified: {audit['count']}",
    ]
    if not audit["ok"]:
        lines += [f"- Broken at: {audit['broken_at']}", f"- Detail: {audit['detail']}"]
    lines += [
        "",
        "## Active compliance settings",
        f"- Enabled packs: {', '.join(pack['policy']['enabled']) or '(baseline)'}",
        f"- Controls with provenance: {len(pack['policy']['provenance'])}",
        "",
        "## Egress (what left the machine)",
        f"- Events: {egress['total']} "
        f"(approved {egress['approved_count']}, denied {egress['denied_count']})",
        "",
        "## ROPA (GDPR Art. 30)",
        f"- Processing activities: {pack['ropa']['count']}",
    ]
    lines += [f"  - {ref}" for ref in pack["ropa"]["dataset_refs"]]
    lines += ["", "## Backups"]
    if pack["backups"] is None:
        lines.append("- Not provided")
    else:
        lines.append(f"- Backups: {pack['backups']['count']}")
    lines += [
        "",
        "## SBOM (NFR-18)",
        f"- Components: {pack['sbom']['component_count']}",
        "",
    ]
    return "\n".join(lines)


def build_evidence_pack(
    *,
    audit_log: Any,
    registry: Any,
    object_store: Any,
    enabled_packs: Sequence[str] = (),
    out_store: Any,
    backup_service: Optional[Any] = None,
) -> dict[str, Any]:
    """Assemble and store an evidence pack; return its manifest."""
    now = datetime.now(timezone.utc)
    generated_at = now.isoformat()
    verify = audit_log.verify()
    effective = merge_packs(list(enabled_packs))
    egress = build_egress_report(audit_log)
    activities = build_ropa(registry, object_store)

    backups = None
    if backup_service is not None:
        items = backup_service.list_backups()
        backups = {
            "count": len(items),
            "backups": [
                {
                    "backup_id": b.backup_id,
                    "created_at": b.created_at,
                    "archive_sha256": b.archive_sha256,
                    "size_bytes": b.size_bytes,
                    "label": b.label,
                }
                for b in items
            ],
        }

    pack: dict[str, Any] = {
        "generated_at": generated_at,
        "note": LEGAL_NOTE,
        "audit": {
            "ok": bool(verify.ok),
            "count": verify.count,
            "broken_at": verify.broken_at,
            "detail": verify.detail,
        },
        "policy": {
            "enabled": list(effective.enabled),
            "settings": _plain(effective.settings),
            "provenance": _plain(effective.provenance),
        },
        "egress": {
            "total": egress.total,
            "approved_count": egress.approved_count,
            "denied_count": egress.denied_count,
            "entries": _plain(egress.entries),
        },
        "ropa": {
            "count": len(activities),
            "dataset_refs": [a.dataset_ref for a in activities],
            "activities": _plain(activities),
        },
        "backups": backups,
        "sbom": build_sbom(),
    }

    ts = now.strftime("%Y%m%dT%H%M%S%fZ")
    pack_key = f"evidence/pack-{ts}.json"
    md_key = f"evidence/pack-{ts}.md"
    out_store.put(pack_key, canonical_json(pack).encode("utf-8"))
    out_store.put(md_key, _render_md(pack).encode("utf-8"))
    return {
        "pack_key": pack_key,
        "md_key": md_key,
        "audit_ok": pack["audit"]["ok"],
        "generated_at": generated_at,
        "sections": list(SECTIONS),
    }


__all__ = ["build_evidence_pack", "LEGAL_NOTE", "SECTIONS"]
