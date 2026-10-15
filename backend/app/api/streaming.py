from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi.concurrency import iterate_in_threadpool

from app.agents.runner import TurnRunner
from app.api.sse import SseEncoder
from app.core.enums import EventType
from app.core.errors import PandaError
from app.core.logging import get_logger
from app.schemas.chat import ChatRequest

log = get_logger("api.stream")
GENERIC_ERROR = "Something went wrong while answering that. Please try again."


class ChatStreamService:
    """Turns one chat request into an SSE event stream: run_started, step*, result, run_finished (or error).
    The graph runs in a worker thread; the event loop only forwards events, sends heartbeats and watches for disconnects."""

    def __init__(self, runner: TurnRunner, heartbeat_s: float) -> None:
        self._runner, self._heartbeat_s = runner, heartbeat_s

    async def stream(self, request: ChatRequest, is_disconnected: Callable[[], Awaitable[bool]]) -> AsyncIterator[str]:
        thread_id = request.thread_id or uuid.uuid4().hex
        started = time.perf_counter()
        yield SseEncoder.event(EventType.RUN_STARTED, {"thread_id": thread_id})
        updates = iterate_in_threadpool(self._runner.stream(
            request.question, thread_id, {"force_raw": request.force_raw, "bypass_cache": request.bypass_cache}))
        final: dict | None = None
        pending = asyncio.ensure_future(anext(updates, None))
        try:
            while True:
                done, _ = await asyncio.wait({pending}, timeout=self._heartbeat_s)
                if not done:
                    if await is_disconnected():
                        log.info("client disconnected, abandoning stream")
                        return
                    yield SseEncoder.heartbeat()
                    continue
                update = pending.result()
                if update is None:
                    break
                for step in update.steps:
                    yield SseEncoder.event(EventType.STEP, step)
                final = update.response or final
                pending = asyncio.ensure_future(anext(updates, None))
        except PandaError as e:
            log.warning("run failed: %s", e.message)
            yield SseEncoder.event(EventType.ERROR, {"code": e.code, "message": e.message if e.user_facing else GENERIC_ERROR})
            return
        except Exception:  # never leave the client with a dropped stream and no explanation
            log.exception("unexpected failure while streaming")
            yield SseEncoder.event(EventType.ERROR, {"code": "internal_error", "message": GENERIC_ERROR})
            return
        finally:
            if not pending.done():
                pending.cancel()
        if final is None:
            yield SseEncoder.event(EventType.ERROR, {"code": "empty_result", "message": GENERIC_ERROR})
            return
        final.setdefault("meta", {})["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
        yield SseEncoder.event(EventType.RESULT, final)
        yield SseEncoder.event(EventType.RUN_FINISHED, {"thread_id": thread_id})
