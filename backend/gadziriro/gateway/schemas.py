"""Shared API schemas (Pydantic v2). UI (frontend) and CLI code against these."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class PrincipalOut(BaseModel):
    user_id: str
    username: str
    roles: list[str] = Field(default_factory=list)


class SessionOut(BaseModel):
    session_id: str
    kernel_id: Optional[str] = None
    status: str
    gpu_ids: list[int] = Field(default_factory=list)
    allow_egress: bool = False


class HardwareReport(BaseModel):
    """Result of the installer hardware check (FR-27)."""

    gpu_present: bool
    gpu_count: int
    gpu_memory_mb: list[int] = Field(default_factory=list)
    cpu_count: int
    ram_mb: int
    disk_free_gb: float
    supported_methods: list[str] = Field(default_factory=list)
    recommended_model_sizes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AuditVerifyOut(BaseModel):
    ok: bool
    count: int
    broken_at: Optional[int] = None
    detail: str = ""
