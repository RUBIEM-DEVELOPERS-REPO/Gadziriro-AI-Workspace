"""Simple in-memory token-bucket rate-limit middleware.

A per-client token bucket (keyed by remote IP) that refills at a fixed rate and
rejects with HTTP 429 once drained. In-process and single-node only — it exists
to blunt brute-force login attempts and runaway clients in Phase 0; a shared
store (Redis) and per-route policy arrive in Phase 1.
"""

from __future__ import annotations

import threading
import time
from typing import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class TokenBucketMiddleware:
    """Starlette middleware applying one refilling token bucket per client IP."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        capacity: int = 120,
        refill_per_second: float = 2.0,
    ) -> None:
        """Configure the bucket.

        :param capacity: maximum burst (tokens) per client.
        :param refill_per_second: tokens added back each second.
        """
        self.app = app
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def _allow(self, key: str) -> bool:
        """Consume one token for ``key``; return whether it was available."""
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill_per_second)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1.0, now)
            return True

    async def __call__(
        self,
        scope: dict,
        receive: Callable[[], Awaitable[dict]],
        send: Callable[[dict], Awaitable[None]],
    ) -> None:
        """Rate-limit HTTP requests; pass through everything else."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        client = request.client.host if request.client else "anonymous"
        if not self._allow(client):
            response: Response = JSONResponse(
                {"detail": "rate limit exceeded"}, status_code=429
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
