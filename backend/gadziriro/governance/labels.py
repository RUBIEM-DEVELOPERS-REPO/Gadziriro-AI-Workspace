"""Dataset sensitivity labels (FR-08). Shared by registry and governance.

Ordered least-to-most sensitive so policy can compare and apply the strictest
control by default (BRD §18).
"""

from __future__ import annotations

from enum import Enum


class SensitivityLabel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PERSONAL = "personal"  # personal data (GDPR / ZW DPA)
    PHI = "phi"  # protected health information (HIPAA)

    @property
    def rank(self) -> int:
        order = {"public": 0, "internal": 1, "personal": 2, "phi": 3}
        return order[self.value]

    @classmethod
    def strictest(cls, labels: list["SensitivityLabel"]) -> "SensitivityLabel":
        """Return the most sensitive label (default-strict precedence)."""
        if not labels:
            return cls.INTERNAL
        return max(labels, key=lambda la: la.rank)
