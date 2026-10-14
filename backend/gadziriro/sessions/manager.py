"""Session & kernel manager (FR-01, FR-03).

A session is one user's sealed notebook environment. The manager starts a kernel
through an injected :class:`RuntimeAdapter`, tracks the live sessions, and tears
them down — releasing the GPU on stop. It never talks to hardware directly; the
adapter is the only path to GPUs and containers.

Privacy default (FR-20): sessions are created with ``allow_egress=False``, so the
underlying kernel is sealed off from the network unless an admin path opens it.

Auditing is optional: if an :class:`~gadziriro.audit.base.AuditSink` is injected,
``session.start`` / ``session.stop`` events are appended; otherwise auditing is
skipped so the manager never hard-depends on the audit implementation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..audit.base import AuditEvent, AuditSink
from ..core.errors import NotFound, RuntimeAdapterError
from ..gateway.schemas import SessionOut
from ..runtime.base import KernelSpec, RuntimeAdapter


@dataclass
class _SessionRecord:
    """Internal bookkeeping for one live session."""

    session_id: str
    user: str
    kernel_id: str
    status: str
    gpu_ids: list[int] = field(default_factory=list)
    allow_egress: bool = False
    # Wall-clock of the last activity on this session (create / run_cell). Used by
    # the idle GPU reclaimer (FR-04) to find sessions that have gone quiet.
    last_active: float = 0.0

    def to_out(self) -> SessionOut:
        """Project this record onto the shared API schema."""
        return SessionOut(
            session_id=self.session_id,
            kernel_id=self.kernel_id,
            status=self.status,
            gpu_ids=list(self.gpu_ids),
            allow_egress=self.allow_egress,
        )


class SessionManager:
    """Create, track, and tear down sealed notebook sessions."""

    def __init__(
        self,
        adapter: RuntimeAdapter,
        *,
        audit: Optional[AuditSink] = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        """Wire the manager to a runtime adapter and an optional audit sink.

        ``now`` is an injectable monotonic-ish clock (defaults to ``time.time``)
        so idle tracking can be driven by a fake clock in tests (FR-04).
        """
        self._adapter = adapter
        self._audit = audit
        self._now = now
        self._sessions: dict[str, _SessionRecord] = {}

    # -- lifecycle -------------------------------------------------------

    def create_session(
        self,
        session_id: str,
        user: str,
        gpu_memory_mb: int = 0,
        *,
        allow_egress: bool = False,
    ) -> SessionOut:
        """Start a sealed kernel for ``session_id`` and record the session.

        A GPU is reserved only when ``gpu_memory_mb > 0``; otherwise the session
        is CPU-only. The kernel inherits ``allow_egress`` (default ``False`` =
        no network). Returns a :class:`SessionOut`.

        :raises RuntimeAdapterError: if the session id is already in use.
        """
        if session_id in self._sessions:
            raise RuntimeAdapterError(f"session already exists: {session_id}")

        gpu = None
        if gpu_memory_mb > 0:
            gpu = self._adapter.allocate_gpu(gpu_memory_mb)

        spec = KernelSpec(
            session_id=session_id,
            gpu=gpu,
            allow_egress=allow_egress,
        )
        try:
            handle = self._adapter.start_kernel(spec)
        except Exception:
            # Kernel failed to start; the adapter owns GPU-pool reclaim, so we
            # just propagate. A dedicated release hook arrives with the Phase 1
            # scheduler.
            raise

        record = _SessionRecord(
            session_id=session_id,
            user=user,
            kernel_id=handle.kernel_id,
            status="running",
            gpu_ids=list(gpu.gpu_ids) if gpu else [],
            allow_egress=allow_egress,
            last_active=self._now(),
        )
        self._sessions[session_id] = record

        self._log(
            action="session.start",
            actor=user,
            target=session_id,
            meta={
                "kernel_id": handle.kernel_id,
                "gpu_ids": record.gpu_ids,
                "allow_egress": allow_egress,
            },
        )
        return record.to_out()

    def stop_session(self, session_id: str) -> None:
        """Stop a session's kernel and release its GPU.

        :raises NotFound: if the session does not exist.
        """
        record = self._require(session_id)
        self._adapter.stop(record.kernel_id)
        del self._sessions[session_id]
        self._log(
            action="session.stop",
            actor=record.user,
            target=session_id,
            meta={"kernel_id": record.kernel_id},
        )

    # -- queries ---------------------------------------------------------

    def get_session(self, session_id: str) -> SessionOut:
        """Return the session, or raise :class:`NotFound`."""
        return self._require(session_id).to_out()

    def list_sessions(self) -> list[SessionOut]:
        """Return all live sessions."""
        return [rec.to_out() for rec in self._sessions.values()]

    # -- execution (FR-01) ----------------------------------------------

    def run_cell(self, session_id: str, code: str) -> dict:
        """Execute one cell in the session's kernel and return its output.

        Delegates to the adapter's ``execute`` capability (present on the mock
        backend). The real notebook protocol lands with the scheduler in Phase 1.

        :raises NotFound: if the session does not exist.
        :raises RuntimeAdapterError: if the backend cannot execute interactively.
        """
        record = self._require(session_id)
        execute = getattr(self._adapter, "execute", None)
        if execute is None:
            raise RuntimeAdapterError(
                "runtime backend does not support interactive execute"
            )
        result = execute(record.kernel_id, code)
        # Running a cell counts as activity, so the idle reclaimer leaves it alone.
        record.last_active = self._now()
        return result

    # -- idle tracking (FR-04) ------------------------------------------

    def last_active(self, session_id: str) -> float:
        """Return the timestamp of the session's last activity.

        :raises NotFound: if the session does not exist.
        """
        return self._require(session_id).last_active

    def idle_sessions(
        self,
        timeout_s: float,
        now: Optional[Callable[[], float]] = None,
    ) -> list[str]:
        """Return the ids of sessions idle longer than ``timeout_s``.

        ``now`` optionally overrides the manager's clock (a callable returning a
        timestamp), which lets a fake clock drive reclaim tests deterministically.
        """
        clock = now if now is not None else self._now
        current = clock()
        return [
            sid
            for sid, rec in self._sessions.items()
            if current - rec.last_active > timeout_s
        ]

    # -- helpers ---------------------------------------------------------

    def _require(self, session_id: str) -> _SessionRecord:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise NotFound(f"unknown session: {session_id}") from exc

    def _log(
        self,
        *,
        action: str,
        actor: str,
        target: str,
        meta: dict,
    ) -> None:
        if self._audit is None:
            return
        self._audit.append(
            AuditEvent(actor=actor, action=action, target=target, meta=meta)
        )
