"""Licence and export-control checks for base models (FR-48).

Before a base (or fine-tuned) model is *used* or *exported*, the workspace gates
the action against two policies:

* **Licence** — does the model's licence permit the intended use (commercial vs
  non-commercial, redistribution)?
* **Export control** — is the model export-restricted, and if so, is the
  destination inside the allowed set?

Both are conservative by default: an unknown model family resolves to a record
that assumes the strictest controls, so an unrecognised model never slips through
as unrestricted. The licence table is a plain dict keyed by family prefix that
callers can extend (``register_licence``) for private or newly released models.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from ..core.errors import PolicyDenied


@dataclass(frozen=True)
class LicenceRecord:
    """Licence facts for a model family."""

    name: str
    licence_id: str
    commercial_use: bool
    redistribute: bool
    export_restricted: bool


# Licence table keyed by model-family prefix (lower-cased). Callers may extend it
# via ``register_licence`` for private or newly released families.
LICENCE_TABLE: dict[str, LicenceRecord] = {
    "llama": LicenceRecord(
        name="Llama family",
        licence_id="llama-community",
        commercial_use=True,  # permitted below Meta's MAU threshold
        redistribute=True,
        export_restricted=False,
    ),
    "mistral": LicenceRecord(
        name="Mistral / Mixtral family",
        licence_id="apache-2.0",
        commercial_use=True,
        redistribute=True,
        export_restricted=False,
    ),
    "qwen": LicenceRecord(
        name="Qwen family",
        licence_id="tongyi-qianwen",
        commercial_use=True,
        redistribute=True,
        export_restricted=True,  # PRC-origin weights: treat as export-controlled
    ),
    "falcon": LicenceRecord(
        name="Falcon family",
        licence_id="apache-2.0",
        commercial_use=True,
        redistribute=True,
        export_restricted=False,
    ),
    "research": LicenceRecord(
        name="Research-only family",
        licence_id="non-commercial-research",
        commercial_use=False,
        redistribute=False,
        export_restricted=False,
    ),
}

# A conservative record for unknown families: assume everything is restricted so
# an unrecognised model cannot be used or exported without an explicit entry.
UNKNOWN_LICENCE = LicenceRecord(
    name="unknown",
    licence_id="unknown",
    commercial_use=False,
    redistribute=False,
    export_restricted=True,
)

# Destinations allowed to receive export-restricted models. In a real deployment
# this is configuration; here it is a simple allow-list the checks consult.
ALLOWED_EXPORT_DESTINATIONS: frozenset[str] = frozenset(
    {"domestic", "local", "zw", "zimbabwe"}
)


def register_licence(prefix: str, record: LicenceRecord) -> None:
    """Add or override the licence record for a model-family ``prefix``.

    Lets callers extend the built-in table for private or newly released models.
    """
    LICENCE_TABLE[prefix.lower()] = record


def _record_for(model_or_base: str) -> LicenceRecord:
    """Return the :class:`LicenceRecord` for ``model_or_base`` by family prefix.

    Matching is by longest family prefix against the (lower-cased) model name.
    An unknown family returns :data:`UNKNOWN_LICENCE`, a conservative record that
    assumes non-commercial, non-redistributable and export-restricted.
    """
    name = model_or_base.lower()
    match: Optional[str] = None
    for prefix in LICENCE_TABLE:
        if name.startswith(prefix) and (match is None or len(prefix) > len(match)):
            match = prefix
    if match is None:
        return UNKNOWN_LICENCE
    return LICENCE_TABLE[match]


def licence_for(model_or_base: str) -> dict[str, Any]:
    """Return the licence record for ``model_or_base`` as a plain dict.

    Keys: ``name``, ``licence_id``, ``commercial_use``, ``redistribute``,
    ``export_restricted``. An unknown family yields a conservative record
    (``licence_id="unknown"``) that assumes non-commercial, non-redistributable
    and export-restricted, so an unrecognised model is never treated as free.
    """
    return asdict(_record_for(model_or_base))


def check_licence(model_or_base: str, *, intended_use: str = "commercial") -> None:
    """Gate a model's use against its licence; raise if the use is forbidden.

    ``intended_use`` is ``"commercial"`` or ``"non-commercial"``. A commercial
    use of a non-commercial licence raises :class:`PolicyDenied`. Called BEFORE
    the model is used.
    """
    record = _record_for(model_or_base)
    if intended_use == "commercial" and not record.commercial_use:
        raise PolicyDenied(
            f"licence {record.licence_id!r} for {model_or_base!r} forbids "
            f"commercial use"
        )


def check_export_control(model_or_base: str, *, destination: str) -> None:
    """Gate a model's export against export-control rules; raise if forbidden.

    If the model is export-restricted and ``destination`` is not in
    :data:`ALLOWED_EXPORT_DESTINATIONS`, raise :class:`PolicyDenied`. Called
    BEFORE the model is exported off the workspace.
    """
    record = _record_for(model_or_base)
    if record.export_restricted and destination.lower() not in (
        ALLOWED_EXPORT_DESTINATIONS
    ):
        raise PolicyDenied(
            f"model {model_or_base!r} ({record.licence_id}) is export-restricted; "
            f"destination {destination!r} is not in the allowed set"
        )
