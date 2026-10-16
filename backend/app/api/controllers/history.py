from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool

from app.container import Container
from app.core.logging import get_logger
from app.presentation.a2ui import build_surface
from app.security.auth import AuthUser
from app.security.service import current_user

log = get_logger("api.history")
THREAD_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # same rule as ChatRequest.thread_id


def _surface(response: dict, key: str) -> list | None:
    """The same A2UI surface a live turn gets; the UI falls back to the plain result when it is missing."""
    try:
        return build_surface(response, key)
    except Exception:
        log.warning("a2ui surface build failed for a stored turn", exc_info=True)
        return None


def _valid(thread_id: str) -> str:
    if not THREAD_ID.fullmatch(thread_id):
        raise HTTPException(422, "Invalid thread id.")
    return thread_id


class HistoryController:
    """GET /api/threads, GET|DELETE /api/threads/{id}: the caller's own chat history."""

    def __init__(self, container: Container) -> None:
        self._store, self._feedback = container.history, container.feedback
        self.router = APIRouter(prefix="/api", tags=["history"])
        self.router.add_api_route("/threads", self.list_threads, methods=["GET"])
        self.router.add_api_route("/threads/{thread_id}", self.get_thread, methods=["GET"])
        self.router.add_api_route("/threads/{thread_id}", self.delete_thread, methods=["DELETE"], status_code=204)

    async def list_threads(self, user: AuthUser = Depends(current_user)) -> dict:
        rows = await run_in_threadpool(self._store.list_threads, user.uid)
        return {"threads": [{"id": r["id"], "title": r["title"], "updated_at": r["updated_at"].isoformat(), "turns": r["turns"]} for r in rows]}

    async def get_thread(self, thread_id: str, user: AuthUser = Depends(current_user)) -> dict:
        t = await run_in_threadpool(self._store.get_thread, user.uid, _valid(thread_id))
        if t is None:
            raise HTTPException(404, "Chat not found.")
        return {"id": t["id"], "title": t["title"], "updated_at": t["updated_at"].isoformat(),
                "turns": [{"question": x["question"], "response": x["response"], "surface": _surface(x["response"], f"answer-{thread_id}-{i}"),
                           "created_at": x["created_at"].isoformat()} for i, x in enumerate(t["turns"])]}

    async def delete_thread(self, thread_id: str, user: AuthUser = Depends(current_user)) -> Response:
        await run_in_threadpool(self._store.delete_thread, user.uid, _valid(thread_id))  # idempotent
        try:
            await run_in_threadpool(self._feedback.delete_thread, user.uid, thread_id)
        except Exception:
            log.warning("feedback of a deleted chat not removed", exc_info=True)
        return Response(status_code=204)
