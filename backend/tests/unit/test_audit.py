"""Unit tests for the hash-chained audit log (FR-19)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gadziriro.audit.base import AuditEvent, AuditSink
from gadziriro.audit.log import AuditLog
from gadziriro.core.crypto import GENESIS, hash_record


def _event(action: str) -> AuditEvent:
    return AuditEvent(
        actor="alice",
        action=action,
        target="session:42",
        reason="unit-test",
        level="info",
        meta={"ip": "127.0.0.1"},
    )


def _log(tmp_path: Path) -> AuditLog:
    return AuditLog(path=tmp_path / "audit.jsonl")


def test_implements_audit_sink(tmp_path: Path) -> None:
    assert isinstance(_log(tmp_path), AuditSink)


def test_empty_log_verifies(tmp_path: Path) -> None:
    result = _log(tmp_path).verify()
    assert result.ok is True
    assert result.count == 0
    assert result.broken_at is None


def test_append_returns_record_with_seq_and_hash(tmp_path: Path) -> None:
    log = _log(tmp_path)
    rec = log.append(_event("auth.login"))
    assert rec["seq"] == 1
    assert rec["prev_hash"] == GENESIS
    assert rec["hash"] == hash_record({k: rec[k] for k in rec if k != "hash"})


def test_append_several_and_verify_ok(tmp_path: Path) -> None:
    log = _log(tmp_path)
    for i in range(5):
        log.append(_event(f"action.{i}"))
    result = log.verify()
    assert result.ok is True
    assert result.count == 5
    assert result.broken_at is None


def test_seq_monotonic_and_linkage(tmp_path: Path) -> None:
    log = _log(tmp_path)
    records = [log.append(_event(f"a.{i}")) for i in range(4)]

    # seq counts from 1, strictly +1 each time.
    assert [r["seq"] for r in records] == [1, 2, 3, 4]

    # prev_hash links each record to the previous one; first is GENESIS.
    assert records[0]["prev_hash"] == GENESIS
    for prev, cur in zip(records, records[1:], strict=False):
        assert cur["prev_hash"] == prev["hash"]


def test_each_line_is_canonical_json(tmp_path: Path) -> None:
    log = _log(tmp_path)
    log.append(_event("one"))
    log.append(_event("two"))
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        record = json.loads(line)
        # Hash covers everything except itself.
        recomputed = hash_record({k: record[k] for k in record if k != "hash"})
        assert recomputed == record["hash"]


def test_restart_continues_chain(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    first = AuditLog(path=path)
    r1 = first.append(_event("before.restart"))
    r2 = first.append(_event("also.before"))

    # New instance recovers seq + last hash from the file tail.
    second = AuditLog(path=path)
    r3 = second.append(_event("after.restart"))
    assert r3["seq"] == r2["seq"] + 1 == 3
    assert r3["prev_hash"] == r2["hash"]

    result = second.verify()
    assert result.ok is True
    assert result.count == 3
    assert r1["seq"] == 1


def test_recover_corrupt_tail_raises(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path=path)
    log.append(_event("good"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write("this is not json\n")

    from gadziriro.core.errors import AuditError

    with pytest.raises(AuditError):
        AuditLog(path=path)
