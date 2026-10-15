from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.streaming import ChatStreamService
from app.container import Container
from app.schemas.chat import ChatRequest


class ChatController:
    """POST /api/chat: one conversational turn as a Server-Sent Events stream."""

    def __init__(self, container: Container) -> None:
        self._max_chars = container.settings.max_question_chars
        self._streamer = ChatStreamService(container.runner, container.settings.sse_heartbeat_s)
        self.router = APIRouter(prefix="/api", tags=["chat"])
        self.router.add_api_route("/chat", self.chat, methods=["POST"], response_class=StreamingResponse)

    async def chat(self, body: ChatRequest, request: Request) -> StreamingResponse:
        if len(body.question) > self._max_chars:
            raise HTTPException(422, f"Question is too long (max {self._max_chars} characters).")
        return StreamingResponse(
            self._streamer.stream(body, request.is_disconnected), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
