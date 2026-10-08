"""FastAPI gateway — the single HTTP entry point (FR wiring).

:func:`create_app` builds the application and lets callers inject the user store,
session manager, and audit sink (tests pass fakes / temp sqlite); missing deps
default to the production wiring (sqlite user store, mock-or-docker runtime,
hash-chained audit log). A module-level ``app = create_app()`` keeps the
``gadziriro.gateway.app:app`` import path that the Makefile, Dockerfile, and CI
depend on.

Cross-cutting concerns live here: the project exception hierarchy is translated
to HTTP status codes, a token-bucket rate limiter guards every route, and CORS
is opened for the Vite dev origin.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..audit.base import AuditSink
from ..audit.log import AuditLog
from ..auth.store import SqlUserStore
from ..core.config import Settings, load_settings
from ..core.errors import AuthError, GadziriroError, NotFound, PolicyDenied
from ..runtime.factory import get_runtime_adapter
from ..sessions.manager import SessionManager
from . import routes  # noqa: F401 - import registers the four routers
from .ratelimit import TokenBucketMiddleware
from .registry import registered_routers

VITE_DEV_ORIGIN = "http://localhost:5173"


def _install_exception_handlers(app: FastAPI) -> None:
    """Map the project exception hierarchy onto HTTP status codes."""

    def _handler(status_code: int):
        async def handle(_: Request, exc: Exception) -> JSONResponse:
            return JSONResponse({"detail": str(exc)}, status_code=status_code)

        return handle

    # Most specific first; GadziriroError is the catch-all for the rest.
    app.add_exception_handler(AuthError, _handler(401))
    app.add_exception_handler(PolicyDenied, _handler(403))
    app.add_exception_handler(NotFound, _handler(404))
    app.add_exception_handler(GadziriroError, _handler(400))


def create_app(
    settings: Optional[Settings] = None,
    *,
    user_store: Optional[SqlUserStore] = None,
    session_manager: Optional[SessionManager] = None,
    audit: Optional[AuditSink] = None,
) -> FastAPI:
    """Build the gateway application.

    Any of ``user_store`` / ``session_manager`` / ``audit`` may be injected
    (tests pass fakes and temp-sqlite stores); whatever is omitted is built from
    ``settings`` (defaulting to :func:`load_settings`). Dependencies are stored
    on ``app.state`` and read by the route dependencies.
    """
    settings = settings or load_settings()
    settings.ensure_dirs()

    audit = audit or AuditLog(settings=settings)
    user_store = user_store or SqlUserStore(settings)
    session_manager = session_manager or SessionManager(
        get_runtime_adapter(settings), audit=audit
    )

    app = FastAPI(title="Gadziriro AI Workspace", version="0.1.0")
    app.state.settings = settings
    app.state.audit = audit
    app.state.user_store = user_store
    app.state.session_manager = session_manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[VITE_DEV_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TokenBucketMiddleware)

    _install_exception_handlers(app)

    mounted: set[int] = set()
    for prefix, router in registered_routers():
        if id(router) in mounted:
            continue
        mounted.add(id(router))
        app.include_router(router, prefix=prefix)

    return app


app = create_app()
