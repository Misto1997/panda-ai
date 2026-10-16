from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.api.streaming import ChatStreamService
from app.container import Container
from app.llm.budget import open_turn_budget
from app.security.auth import AuthUser
from app.security.service import authenticated_user
from app.schemas.chat import ChatRequest


class ChatController:
    """POST /api/chat: one conversational turn as a Server-Sent Events stream."""

    def __init__(self, container: Container) -> None:
        self._max_chars = container.settings.max_question_chars
        self._quota, self._llm_calls = container.security.quota, container.settings.llm_max_calls_per_turn
        self._streamer = ChatStreamService(container.runner, container.settings.sse_heartbeat_s)
        self.router = APIRouter(prefix="/api", tags=["chat"])
        self.router.add_api_route("/chat", self.chat, methods=["POST"], response_class=StreamingResponse)

    async def chat(self, body: ChatRequest, request: Request, user: AuthUser = Depends(authenticated_user)) -> StreamingResponse:
        if len(body.question) > self._max_chars:
            raise HTTPException(422, f"Question is too long (max {self._max_chars} characters).")
        await run_in_threadpool(self._quota.consume, user)  # one unit per turn; 401/429 above and here happen before any LLM call
        open_turn_budget(self._llm_calls)
        return StreamingResponse(
            self._streamer.stream(body, request.is_disconnected), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
