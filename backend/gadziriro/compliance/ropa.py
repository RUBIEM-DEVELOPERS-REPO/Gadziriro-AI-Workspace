"""Records of Processing Activities (ROPA, GDPR Art. 30) — FR-46.

Builds the register of personal-data processing from the dataset registry: one
activity per dataset version that carries personal data (sensitivity PERSONAL or PHI).
Public/internal datasets are not personal data and are excluded.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

from ..core.canonical_json import canonical_json
from ..governance.labels import SensitivityLabel

_PERSONAL = {SensitivityLabel.PERSONAL, SensitivityLabel.PHI}


@dataclass(frozen=True)
class ProcessingActivity:
    dataset_ref: str
    purpose: str
    data_categories: tuple[str, ...]
    source: str
    sensitivity: str
    lawful_basis: str = "legitimate_interest"
    controller: str = "customer"
    processor: str = "Gadziriro"


def _categories(label: SensitivityLabel) -> tuple[str, ...]:
    if label == SensitivityLabel.PHI:
        return ("health_data",)
    if label == SensitivityLabel.PERSONAL:
        return ("personal_data",)
    return ("non_personal",)


def _dataset_names(store) -> list[str]:
    names: set[str] = set()
    for key in store.list("datasets"):
        # keys look like datasets/<name>/<version>/meta.json
        parts = key.split("/")
        if len(parts) >= 2 and parts[0] == "datasets":
            names.add(parts[1])
    return sorted(names)


def build_ropa(
    registry,
    store,
    *,
    controller: str = "customer",
    processor: str = "Gadziriro",
    purposes: Optional[dict[str, str]] = None,
    lawful_basis: str = "legitimate_interest",
) -> list[ProcessingActivity]:
    """Build one ProcessingActivity per personal-data dataset version."""
    purposes = purposes or {}
    activities: list[ProcessingActivity] = []
    for name in _dataset_names(store):
        for dv in registry.list_dataset_versions(name):
            label = dv.sensitivity
            if label not in _PERSONAL:
                continue
            activities.append(
                ProcessingActivity(
                    dataset_ref=dv.ref,
                    purpose=purposes.get(name, "model training / evaluation"),
                    data_categories=_categories(label),
                    source=dv.source,
                    sensitivity=label.value,
                    lawful_basis=lawful_basis,
                    controller=controller,
                    processor=processor,
                )
            )
    return activities


def export_ropa(activities: list[ProcessingActivity], out_store) -> str:
    """Write the ROPA register as JSON + markdown; return the JSON key."""
    records = [asdict(a) for a in activities]
    key = "ropa/ropa.json"
    out_store.put(key, (canonical_json(records) + "\n").encode("utf-8"))
    lines = ["# Records of Processing Activities (ROPA)", ""]
    for a in activities:
        lines.append(
            f"- {a.dataset_ref}: {a.purpose} | {', '.join(a.data_categories)} "
            f"| basis={a.lawful_basis} | source={a.source} | {a.sensitivity}"
        )
    if not activities:
        lines.append("- (no personal-data processing activities)")
    out_store.put("ropa/ropa.md", ("\n".join(lines) + "\n").encode("utf-8"))
    return key
