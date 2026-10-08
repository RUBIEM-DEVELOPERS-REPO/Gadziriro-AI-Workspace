"""Integration tests for the ``gadziriro`` CLI (cli/main.py)."""

from __future__ import annotations

import json
from pathlib import Path

from gadziriro.audit.base import AuditEvent
from gadziriro.audit.log import AuditLog
from gadziriro.cli.main import main


def _seed_chain(audit_dir: Path, count: int = 3) -> Path:
    """Write ``count`` valid chained records under ``audit_dir`` and return it."""
    log = AuditLog(path=audit_dir / "audit.jsonl")
    for index in range(count):
        log.append(
            AuditEvent(
                actor="tester",
                action="test.event",
                target=f"t{index}",
                reason="ok",
            )
        )
    return audit_dir


def test_hw_check_returns_zero_and_prints_report(capsys) -> None:
    assert main(["hw-check"]) == 0
    out = capsys.readouterr().out
    assert "hardware check" in out.lower()
    assert "CPU count" in out
    assert "Supported methods" in out


def test_audit_verify_ok_returns_zero(tmp_path, capsys) -> None:
    audit_dir = _seed_chain(tmp_path)
    assert main(["audit", "verify", "--audit-dir", str(audit_dir)]) == 0
    assert "OK" in capsys.readouterr().out


def test_audit_verify_tampered_returns_one(tmp_path, capsys) -> None:
    audit_dir = _seed_chain(tmp_path)
    path = audit_dir / "audit.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["actor"] = "attacker"  # mutate a hashed field, leave hash stale
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert main(["audit", "verify", "--audit-dir", str(audit_dir)]) == 1
    assert "BROKEN" in capsys.readouterr().out


def test_openapi_writes_valid_document(tmp_path) -> None:
    out = tmp_path / "openapi.json"
    assert main(["openapi", "--out", str(out)]) == 0

    document = json.loads(out.read_text(encoding="utf-8"))
    assert "openapi" in document
    assert "/api/auth/login" in document["paths"]


def test_openapi_to_stdout(capsys) -> None:
    assert main(["openapi"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert "openapi" in document
