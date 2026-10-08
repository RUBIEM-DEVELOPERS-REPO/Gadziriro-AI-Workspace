"""Unit tests for the session manager (create/track/teardown, audit, isolation)."""

from __future__ import annotations

from typing import Any

import pytest

from gadziriro.audit.base import AuditEvent, VerifyResult
from gadziriro.core.errors import NotFound, RuntimeAdapterError
from gadziriro.runtime.mock import MockRuntimeAdapter
from gadziriro.sessions.manager import SessionManager


class FakeAudit:
    """A minimal AuditSink for asserting that lifecycle events are emitted."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> dict[str, Any]:
        self.events.append(event)
        return {"seq": len(self.events), "action": event.action}

    def verify(self) -> VerifyResult:
        return VerifyResult(ok=True, count=len(self.events))


def test_create_get_list_stop() -> None:
    mgr = SessionManager(MockRuntimeAdapter(gpu_count=1))
    out = mgr.create_session("s1", user="alice")
    assert out.session_id == "s1"
    assert out.status == "running"
    assert mgr.get_session("s1").kernel_id == out.kernel_id
    assert len(mgr.list_sessions()) == 1
    mgr.stop_session("s1")
    assert mgr.list_sessions() == []


def test_duplicate_session_rejected() -> None:
    mgr = SessionManager(MockRuntimeAdapter(gpu_count=1))
    mgr.create_session("s1", user="alice")
    with pytest.raises(RuntimeAdapterError):
        mgr.create_session("s1", user="alice")


def test_gpu_released_on_stop() -> None:
    adapter = MockRuntimeAdapter(gpu_count=1, gpu_memory_mb=24000)
    mgr = SessionManager(adapter)
    out = mgr.create_session("s1", user="alice", gpu_memory_mb=24000)
    assert out.gpu_ids  # a device was assigned
    assert adapter.metrics().gpus_free == 0
    mgr.stop_session("s1")
    assert adapter.metrics().gpus_free == 1


def test_two_sessions_isolated() -> None:
    adapter = MockRuntimeAdapter(gpu_count=2, gpu_memory_mb=24000)
    mgr = SessionManager(adapter)
    a = mgr.create_session("a", user="u1", gpu_memory_mb=24000)
    b = mgr.create_session("b", user="u2", gpu_memory_mb=24000)
    assert a.kernel_id != b.kernel_id
    assert set(a.gpu_ids).isdisjoint(b.gpu_ids)


def test_default_session_has_no_egress() -> None:
    mgr = SessionManager(MockRuntimeAdapter(gpu_count=1))
    out = mgr.create_session("s1", user="alice")
    assert out.allow_egress is False


def test_audit_events_emitted_when_sink_injected() -> None:
    audit = FakeAudit()
    mgr = SessionManager(MockRuntimeAdapter(gpu_count=1), audit=audit)
    mgr.create_session("s1", user="alice")
    mgr.stop_session("s1")
    actions = [e.action for e in audit.events]
    assert actions == ["session.start", "session.stop"]


def test_no_audit_when_sink_absent() -> None:
    # Must not hard-depend on the audit implementation.
    mgr = SessionManager(MockRuntimeAdapter(gpu_count=1), audit=None)
    mgr.create_session("s1", user="alice")  # no exception
    mgr.stop_session("s1")


def test_stop_unknown_session_raises() -> None:
    mgr = SessionManager(MockRuntimeAdapter(gpu_count=1))
    with pytest.raises(NotFound):
        mgr.stop_session("nope")
