"""Cheap abuse guards in front of the LLM: per-IP token bucket and a request body size cap."""
from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import RateLimitedError, RequestTooLargeError


class IpRateLimiter:
    """In-memory token bucket per client IP (per instance). `rate_per_minute` refill, `burst` capacity."""

    MAX_TRACKED = 10_000

    def __init__(self, rate_per_minute: int, burst: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._rate, self._burst, self._clock = rate_per_minute / 60.0, float(burst), clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def check(self, ip: str) -> None:
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(ip, (self._burst, now))
            tokens = min(self._burst, tokens + (now - last) * self._rate)
            if tokens < 1.0:
                self._buckets[ip] = (tokens, now)
                raise RateLimitedError("Too many requests. Slow down and try again in a moment.")
            if len(self._buckets) >= self.MAX_TRACKED:
                self._buckets.clear()  # crude eviction; only reachable under a flood of distinct IPs
            self._buckets[ip] = (tokens - 1.0, now)


def client_ip(headers, peer: str | None) -> str:
    """Cloud Run puts the client first in X-Forwarded-For (uvicorn --proxy-headers would also set the peer)."""
    forwarded = headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or peer or "unknown"


class BodyLimitMiddleware:
    """Rejects request bodies above `max_bytes` with 413, by Content-Length and by counting streamed bytes."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declared = dict(scope["headers"]).get(b"content-length", b"0")
        if declared.isdigit() and int(declared) > self.max_bytes:
            return await self._reject(send)
        seen = 0
        started = False

        async def counted() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise RequestTooLargeError("Request body too large.")
            return message

        async def tracked(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counted, tracked)
        except RequestTooLargeError:
            if not started:
                await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        body = json.dumps({"code": RequestTooLargeError.code, "message": "Request body too large."}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
