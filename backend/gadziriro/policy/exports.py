"""Export-approval policy and request workflow (FR-21).

Exporting a dataset or model out of the workspace is gated by *sensitivity*:

* ``PUBLIC`` / ``INTERNAL`` exports are **auto-approved** — low-risk data may
  leave without a human in the loop.
* ``PERSONAL`` / ``PHI`` exports **always require approval** — personal data
  (GDPR / ZW DPA) and protected health information (HIPAA) may only leave the
  workspace once a human approver has signed off.

The rule is explicit and configurable: :class:`ExportPolicy` is constructed with
the set of :class:`~gadziriro.governance.labels.SensitivityLabel` values that
require approval (defaulting to ``{PERSONAL, PHI}``).

The workflow is: :meth:`ExportPolicy.request_export` opens an
:class:`ExportRequest` that is either ``"pending"`` (approval required) or
``"auto-approved"`` (low-risk). :meth:`ExportPolicy.approve` /
:meth:`ExportPolicy.deny` move a pending request to ``"approved"`` / ``"denied"``.
Every state change is written to the :class:`~gadziriro.audit.base.AuditSink`
(``export.request`` / ``export.approve`` / ``export.deny``).
:meth:`ExportPolicy.assert_export_allowed` raises
:class:`~gadziriro.core.errors.PolicyDenied` when an export whose request is not
(auto-)approved is attempted.

Requests are held in memory — sufficient for Phase 0/1; a persistent store can
replace the dict without changing the surface.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Optional, Union

from ..audit.base import AuditEvent, AuditSink
from ..core.errors import NotFound, PolicyDenied
from ..governance.labels import SensitivityLabel

__all__ = [
    "ExportRequest",
    "ExportPolicy",
    "DEFAULT_APPROVAL_REQUIRED",
    "STATUS_PENDING",
    "STATUS_AUTO_APPROVED",
    "STATUS_APPROVED",
    "STATUS_DENIED",
]

STATUS_PENDING = "pending"
STATUS_AUTO_APPROVED = "auto-approved"
STATUS_APPROVED = "approved"
STATUS_DENIED = "denied"

# Statuses for which an export may actually proceed.
_ALLOWED_STATUSES = frozenset({STATUS_AUTO_APPROVED, STATUS_APPROVED})

# Default rule (BRD §18, default-strict): personal data and PHI always need a
# human approver; public/internal data is auto-approved.
DEFAULT_APPROVAL_REQUIRED: frozenset[SensitivityLabel] = frozenset(
    {SensitivityLabel.PERSONAL, SensitivityLabel.PHI}
)


def _now_iso() -> str:
    """Return the current time as an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _coerce_label(sensitivity: Union[SensitivityLabel, str]) -> SensitivityLabel:
    """Return a :class:`SensitivityLabel` from a label or its string value."""
    if isinstance(sensitivity, SensitivityLabel):
        return sensitivity
    return SensitivityLabel(sensitivity)


@dataclass(frozen=True)
class ExportRequest:
    """One request to export a dataset/model out of the workspace (FR-21).

    Attributes:
        request_id: Unique identifier for the request.
        resource_ref: The resource being exported (e.g. ``"patients@3"``).
        sensitivity: The resource's sensitivity label (drives the rule).
        requested_by: The principal who asked for the export.
        status: One of ``"pending"``, ``"auto-approved"``, ``"approved"``,
            ``"denied"``.
        created_at: ISO-8601 UTC timestamp the request was opened.
        decided_by: The approver/denier, once a decision is made.
        decided_at: ISO-8601 UTC timestamp of the decision, if any.
        reason: Free-text reason recorded on a denial.
    """

    request_id: str
    resource_ref: str
    sensitivity: SensitivityLabel
    requested_by: str
    status: str
    created_at: str
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    reason: str = ""

    @property
    def is_allowed(self) -> bool:
        """True when an export may proceed (auto-approved or approved)."""
        return self.status in _ALLOWED_STATUSES


class ExportPolicy:
    """Decide and track export approvals (FR-21).

    The approval rule is configurable via ``approval_required_labels``; every
    state change is logged to the optional ``audit`` sink. Requests are kept in
    an in-memory dict keyed by ``request_id``.
    """

    def __init__(
        self,
        *,
        audit: Optional[AuditSink] = None,
        approval_required_labels: frozenset[SensitivityLabel] = (
            DEFAULT_APPROVAL_REQUIRED
        ),
    ) -> None:
        """Create the policy.

        Args:
            audit: Optional audit sink; every request/approve/deny is appended.
            approval_required_labels: Sensitivity labels that force human
                approval. Defaults to :data:`DEFAULT_APPROVAL_REQUIRED`.
        """
        self._audit = audit
        self._approval_required = frozenset(approval_required_labels)
        self._requests: dict[str, ExportRequest] = {}

    # -- rule ---------------------------------------------------------------

    def requires_approval(self, sensitivity: Union[SensitivityLabel, str]) -> bool:
        """Return whether an export of ``sensitivity`` needs human approval."""
        return _coerce_label(sensitivity) in self._approval_required

    # -- workflow -----------------------------------------------------------

    def request_export(
        self,
        resource_ref: str,
        sensitivity: Union[SensitivityLabel, str],
        requested_by: str,
    ) -> ExportRequest:
        """Open an export request for ``resource_ref`` (FR-21).

        A request for a sensitivity that requires approval is created
        ``"pending"``; otherwise it is immediately ``"auto-approved"``. The
        request is persisted and the event is audited.

        Returns:
            The created :class:`ExportRequest`.
        """
        label = _coerce_label(sensitivity)
        needs_approval = label in self._approval_required
        now = _now_iso()
        request = ExportRequest(
            request_id=f"exp-{uuid.uuid4().hex[:12]}",
            resource_ref=resource_ref,
            sensitivity=label,
            requested_by=requested_by,
            status=STATUS_PENDING if needs_approval else STATUS_AUTO_APPROVED,
            created_at=now,
            decided_by=None if needs_approval else "system",
            decided_at=None if needs_approval else now,
        )
        self._requests[request.request_id] = request
        self._log(
            "export.request",
            actor=requested_by,
            target=resource_ref,
            reason=request.status,
            meta={
                "request_id": request.request_id,
                "sensitivity": label.value,
                "status": request.status,
            },
        )
        return request

    def approve(self, request_id: str, approver: str) -> ExportRequest:
        """Approve a pending export request (FR-21).

        Args:
            request_id: The request to approve.
            approver: The principal granting approval.

        Raises:
            NotFound: if ``request_id`` is unknown.
            PolicyDenied: if the request is not pending.
        """
        request = self.get_request(request_id)
        if request.status != STATUS_PENDING:
            raise PolicyDenied(
                f"export request {request_id} is {request.status}, not pending"
            )
        updated = replace(
            request,
            status=STATUS_APPROVED,
            decided_by=approver,
            decided_at=_now_iso(),
        )
        self._requests[request_id] = updated
        self._log(
            "export.approve",
            actor=approver,
            target=request.resource_ref,
            reason="approved",
            meta={"request_id": request_id, "sensitivity": request.sensitivity.value},
        )
        return updated

    def deny(self, request_id: str, approver: str, reason: str) -> ExportRequest:
        """Deny a pending export request with ``reason`` (FR-21).

        Args:
            request_id: The request to deny.
            approver: The principal denying the request.
            reason: Why the request was denied (recorded + audited).

        Raises:
            NotFound: if ``request_id`` is unknown.
            PolicyDenied: if the request is not pending.
        """
        request = self.get_request(request_id)
        if request.status != STATUS_PENDING:
            raise PolicyDenied(
                f"export request {request_id} is {request.status}, not pending"
            )
        updated = replace(
            request,
            status=STATUS_DENIED,
            decided_by=approver,
            decided_at=_now_iso(),
            reason=reason,
        )
        self._requests[request_id] = updated
        self._log(
            "export.deny",
            actor=approver,
            target=request.resource_ref,
            reason=reason,
            level="security",
            meta={"request_id": request_id, "sensitivity": request.sensitivity.value},
        )
        return updated

    def assert_export_allowed(self, request_id: str) -> ExportRequest:
        """Return the request if its export may proceed, else raise (FR-21).

        Args:
            request_id: The request guarding the attempted export.

        Returns:
            The (auto-)approved :class:`ExportRequest`.

        Raises:
            NotFound: if ``request_id`` is unknown.
            PolicyDenied: if the request is pending or denied.
        """
        request = self.get_request(request_id)
        if not request.is_allowed:
            raise PolicyDenied(
                f"export of {request.resource_ref!r} not approved "
                f"(request {request_id} is {request.status})"
            )
        return request

    # -- queries ------------------------------------------------------------

    def get_request(self, request_id: str) -> ExportRequest:
        """Return one request, or raise :class:`NotFound`."""
        try:
            return self._requests[request_id]
        except KeyError as exc:
            raise NotFound(f"unknown export request: {request_id}") from exc

    def list_requests(self) -> list[ExportRequest]:
        """Return every known export request in creation order."""
        return list(self._requests.values())

    # -- internals ----------------------------------------------------------

    def _log(
        self,
        action: str,
        *,
        actor: str,
        target: str,
        reason: str,
        level: str = "info",
        meta: Optional[dict] = None,
    ) -> None:
        """Append an audit event when an audit sink is wired."""
        if self._audit is None:
            return
        self._audit.append(
            AuditEvent(
                actor=actor,
                action=action,
                target=target,
                reason=reason,
                level=level,
                meta=dict(meta or {}),
            )
        )
