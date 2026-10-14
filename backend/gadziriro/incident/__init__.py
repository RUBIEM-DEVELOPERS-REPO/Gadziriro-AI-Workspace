"""Gadziriro incident response (FR-38, Phase 2 Model Studio).

Tracks security incidents through an audited lifecycle and assembles draft
breach-notification reports for the regulator workflow.
"""

from __future__ import annotations

from .response import Incident, IncidentService, build_breach_report

__all__ = ["Incident", "IncidentService", "build_breach_report"]
