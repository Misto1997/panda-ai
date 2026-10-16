from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi.concurrency import iterate_in_threadpool

from app.agents.runner import TurnRunner
from app.api.sse import AgUiEncoder
from app.core.enums import ErrorCode
from app.core.errors import PandaError
from app.core.logging import get_logger
from app.history import HistoryStore
from app.presentation.a2ui import build_surface
from app.schemas.agui import AgUiEvents
from app.schemas.chat import ChatRequest

log = get_logger("api.stream")
RECORDED_TYPES = {"answer", "rca", "info"}  # errors are not worth reopening
GENERIC_ERROR = "Something went wrong while answering that. Please try again."


class ChatStreamService:
    """Turns one chat request into an AG-UI event stream: RUN_STARTED, steps, text message, A2UI surface, panda.result, RUN_FINISHED (or RUN_ERROR).
    The graph runs in a worker thread; the event loop only forwards events, sends heartbeats and watches for disconnects."""

    def __init__(self, runner: TurnRunner, heartbeat_s: float, history: HistoryStore | None = None) -> None:
        self._runner, self._heartbeat_s, self._history = runner, heartbeat_s, history

    async def stream(self, request: ChatRequest, is_disconnected: Callable[[], Awaitable[bool]], owner: str = "") -> AsyncIterator[str]:
        thread_id = request.thread_id or uuid.uuid4().hex
        state_key = f"{owner}:{thread_id}" if owner else thread_id  # conversations are private to the signed-in user
        started = time.perf_counter()
        ev = AgUiEvents(thread_id, request.run_id or uuid.uuid4().hex)
        enc = AgUiEncoder
        yield enc.encode(ev.run_started())
        updates = iterate_in_threadpool(self._runner.stream(
            request.question, state_key, {"force_raw": request.force_raw, "bypass_cache": request.bypass_cache}))
        final: dict | None = None
        pending = asyncio.ensure_future(anext(updates, None))
        try:
            while True:
                done, _ = await asyncio.wait({pending}, timeout=self._heartbeat_s)
                if not done:
                    if await is_disconnected():
                        log.info("client disconnected, abandoning stream")
                        return
                    yield AgUiEncoder.heartbeat()
                    continue
                update = pending.result()
                if update is None:
                    break
                if update.started:
                    for event in ev.step_running(update.node):
                        yield enc.encode(event)
                elif not update.steps:
                    for event in ev.step_skipped(update.node):
                        yield enc.encode(event)
                for step in update.steps:
                    for event in ev.step(step):
                        yield enc.encode(event)
                if update.response:  # data first: show it the moment it exists; a later (narrated) response replaces it
                    final = update.response
                    for chunk in self._result_events(ev, final, started):
                        yield chunk
                pending = asyncio.ensure_future(anext(updates, None))
        except PandaError as e:
            log.warning("run failed: %s", e.message)
            yield enc.encode(ev.run_error(e.message if e.user_facing else GENERIC_ERROR, e.code))
            return
        except Exception:  # never leave the client with a dropped stream and no explanation
            log.exception("unexpected failure while streaming")
            yield enc.encode(ev.run_error(GENERIC_ERROR, ErrorCode.INTERNAL))
            return
        finally:
            if not pending.done():
                pending.cancel()
        if final is None:
            yield enc.encode(ev.run_error(GENERIC_ERROR, ErrorCode.EMPTY_RESULT))
            return
        self._record(owner, thread_id, request.question, final)
        yield enc.encode(ev.run_finished())

    def _record(self, owner: str, thread_id: str, question: str, response: dict) -> None:
        """Fire and forget: history is best effort and must neither delay nor fail the stream."""
        if self._history is None or not owner or response.get("type") not in RECORDED_TYPES:
            return
        history = self._history

        def write() -> None:
            try:
                history.record(owner, thread_id, question, response)
            except Exception:
                log.warning("could not record chat history", exc_info=True)

        try:
            threading.Thread(target=write, name="history-write", daemon=True).start()
        except Exception:
            log.warning("could not start history write", exc_info=True)

    @staticmethod
    def _result_events(ev: AgUiEvents, response: dict, started: float) -> list[str]:
        """Text, A2UI surface and full payload for one response. Sent again (replacing the first) if the answer is upgraded."""
        enc = AgUiEncoder
        out: list[str] = []
        response.setdefault("meta", {})["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
        try:
            surface = build_surface(response, f"answer-{ev.run_id}")
        except Exception:  # the surface is an enhancement: clients fall back to panda.result
            log.exception("a2ui surface build failed")
            surface = None
        out += [enc.encode(e) for e in ev.text_message(response.get("text", ""))]
        if surface:
            out.append(enc.encode(ev.surface(surface, f"answer-{ev.run_id}")))
        out.append(enc.encode(ev.result(response)))
        return out
