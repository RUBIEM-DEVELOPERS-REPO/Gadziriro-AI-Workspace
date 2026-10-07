"""Shared test fixtures."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from gadziriro.core.config import Settings


@pytest.fixture()
def tmp_settings(monkeypatch) -> Settings:
    """A Settings pointing at an isolated temp data dir, egress OFF (the default)."""
    d = Path(tempfile.mkdtemp(prefix="gadziriro-test-"))
    monkeypatch.setenv("GADZIRIRO_DATA_DIR", str(d))
    monkeypatch.setenv("GADZIRIRO_DATABASE_URL", f"sqlite:///{d / 'test.db'}")
    monkeypatch.setenv("GADZIRIRO_RUNTIME_BACKEND", "mock")
    s = Settings()
    s.ensure_dirs()
    return s
