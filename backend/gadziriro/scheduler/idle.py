"""Idle GPU reclaim (FR-04).

Sessions that have gone quiet keep holding a GPU. The reclaimer asks the
:class:`~gadziriro.sessions.manager.SessionManager` which sessions have been idle
longer than ``timeout_s`` and stops them, which releases their GPUs back to the
pool through the runtime adapter. It never touches hardware itself.

The clock is injectable so reclaim can be tested deterministically with a fake
clock (no sleeping).
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from ..audit.base import AuditEvent
from ..sessions.manager import SessionManager


class IdleReclaimer:
    """Stop sessions idle past a timeout, freeing their GPUs (FR-04)."""

    def __init__(
        self,
        session_manager: SessionManager,
        *,
        timeout_s: float,
        now: Callable[[], float] = time.time,
    ) -> None:
        """Wire the reclaimer to a session manager and an idle ``timeout_s``.

        ``now`` is an injectable clock (callable returning a timestamp).
        """
        self._mgr = session_manager
        self._timeout_s = timeout_s
        self._now = now

    def reclaim(self, now: Optional[Callable[[], float]] = None) -> list[str]:
        """Stop every session idle longer than ``timeout_s``; return their ids.

        ``now`` optionally overrides the reclaimer's clock for this call. Each
        reclaimed session is stopped (releasing its GPU via the adapter) and, if
        the manager carries an audit sink, a ``session.reclaim`` event is logged.
        """
        clock = now if now is not None else self._now
        idle = self._mgr.idle_sessions(self._timeout_s, now=clock)
        reclaimed: list[str] = []
        for session_id in idle:
            # stop_session itself emits session.stop and frees the GPU (FR-04).
            self._mgr.stop_session(session_id)
            reclaimed.append(session_id)
            self._log(session_id)
        return reclaimed

    def _log(self, session_id: str) -> None:
        audit = getattr(self._mgr, "_audit", None)
        if audit is None:
            return
        audit.append(
            AuditEvent(
                actor="system",
                action="session.reclaim",
                target=session_id,
                reason="idle timeout",
                level="info",
                meta={"timeout_s": self._timeout_s},
            )
        )
