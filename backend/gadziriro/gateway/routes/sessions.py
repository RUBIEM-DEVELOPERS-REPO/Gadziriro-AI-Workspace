"""Session routes (FR-01, FR-03) — CRUD over the injected session manager.

Every route requires an authenticated principal. Sessions are created under the
caller's username and sealed from the network by default (``allow_egress`` is
``False`` unless an admin path opens it, FR-20). Execution is delegated to the
runtime adapter via the manager.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...auth.base import Principal
from ...sessions.manager import SessionManager
from ..deps import get_current_principal, get_session_manager
from ..registry import register_router
from ..schemas import SessionOut

router = APIRouter(tags=["sessions"])


class CreateSessionIn(BaseModel):
    """Body for creating a session."""

    session_id: str
    gpu_memory_mb: int = 0
    allow_egress: bool = False


class RunCellIn(BaseModel):
    """Body for executing a single notebook cell."""

    code: str = Field(default="")


@router.get("", response_model=list[SessionOut])
def list_sessions(
    manager: Annotated[SessionManager, Depends(get_session_manager)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> list[SessionOut]:
    """List all live sessions."""
    return manager.list_sessions()


@router.post("", response_model=SessionOut)
def create_session(
    body: CreateSessionIn,
    manager: Annotated[SessionManager, Depends(get_session_manager)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> SessionOut:
    """Create a sealed session for the caller.

    :raises RuntimeAdapterError: if the session id is already in use
        (mapped to HTTP 400).
    """
    return manager.create_session(
        body.session_id,
        user=principal.username,
        gpu_memory_mb=body.gpu_memory_mb,
        allow_egress=body.allow_egress,
    )


@router.get("/{session_id}", response_model=SessionOut)
def get_session(
    session_id: str,
    manager: Annotated[SessionManager, Depends(get_session_manager)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> SessionOut:
    """Return one session.

    :raises NotFound: if the session does not exist (mapped to HTTP 404).
    """
    return manager.get_session(session_id)


@router.post("/{session_id}/stop")
def stop_session(
    session_id: str,
    manager: Annotated[SessionManager, Depends(get_session_manager)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, bool]:
    """Stop a session and release its GPU.

    :raises NotFound: if the session does not exist (mapped to HTTP 404).
    """
    manager.stop_session(session_id)
    return {"ok": True}


@router.post("/{session_id}/run-cell")
def run_cell(
    session_id: str,
    body: RunCellIn,
    manager: Annotated[SessionManager, Depends(get_session_manager)],
    _: Annotated[Principal, Depends(get_current_principal)],
) -> dict:
    """Execute one cell in the session's kernel and return its output.

    :raises NotFound: if the session does not exist (mapped to HTTP 404).
    """
    return manager.run_cell(session_id, body.code)


register_router("/api/sessions", router)
