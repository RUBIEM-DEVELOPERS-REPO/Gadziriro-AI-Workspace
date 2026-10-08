"""FR-19 acceptance (exit-gate): the audit log is tamper-evident.

Append N>=5 records and confirm a fresh ``verify()`` is OK. Then, on *fresh
copies* of the file, apply three classes of tampering — editing a middle
record, deleting a middle line, and swapping two lines — and confirm each makes
a fresh ``verify()`` return ``ok=False`` with ``broken_at`` at the first
affected sequence position.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from gadziriro.audit.base import AuditEvent
from gadziriro.audit.log import AuditLog

N = 6  # >= 5


def _build_log(path: Path) -> None:
    log = AuditLog(path=path)
    for i in range(N):
        log.append(
            AuditEvent(
                actor="system",
                action=f"event.{i}",
                target=f"res:{i}",
                reason="fr19",
                level="security",
                meta={"n": i},
            )
        )


def _fresh_verify(path: Path):
    """Verify from a brand-new instance (ignores any in-memory chain state)."""
    return AuditLog(path=path).verify()


def test_fr19_append_and_verify_ok(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    _build_log(path)
    result = _fresh_verify(path)
    assert result.ok is True
    assert result.count == N
    assert result.broken_at is None


def test_fr19_edit_middle_record_detected(tmp_path: Path) -> None:
    source = tmp_path / "audit.jsonl"
    _build_log(source)

    tampered = tmp_path / "edited.jsonl"
    shutil.copyfile(source, tampered)
    lines = tampered.read_text(encoding="utf-8").splitlines()
    # Edit the 3rd record's action (seq 3) without fixing its hash.
    record = json.loads(lines[2])
    record["action"] = "event.TAMPERED"
    lines[2] = json.dumps(record)
    tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = _fresh_verify(tampered)
    assert result.ok is False
    assert result.broken_at == 3


def test_fr19_delete_middle_line_detected(tmp_path: Path) -> None:
    source = tmp_path / "audit.jsonl"
    _build_log(source)

    tampered = tmp_path / "deleted.jsonl"
    shutil.copyfile(source, tampered)
    lines = tampered.read_text(encoding="utf-8").splitlines()
    # Drop the 3rd record (seq 3); seq 4 now sits where seq 3 should be.
    del lines[2]
    tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = _fresh_verify(tampered)
    assert result.ok is False
    assert result.broken_at == 3


def test_fr19_swap_two_lines_detected(tmp_path: Path) -> None:
    source = tmp_path / "audit.jsonl"
    _build_log(source)

    tampered = tmp_path / "swapped.jsonl"
    shutil.copyfile(source, tampered)
    lines = tampered.read_text(encoding="utf-8").splitlines()
    # Swap records at positions 2 and 3 (seq 2 and seq 3).
    lines[1], lines[2] = lines[2], lines[1]
    tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = _fresh_verify(tampered)
    assert result.ok is False
    assert result.broken_at == 2
