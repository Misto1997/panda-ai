from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.container import Container
from app.core.logging import get_logger
from app.history.feedback import COMMENT_MAX, REASONS_MAX, FeedbackCapReached, clean_reasons, snapshot
from app.security.auth import AuthUser
from app.security.service import current_user

log = get_logger("api.feedback")
THREAD_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # same rule as ChatRequest.thread_id
MAX_TURN = 10_000


class FeedbackRequest(BaseModel):
    thread_id: str = Field(pattern=THREAD_ID.pattern)
    turn: int = Field(ge=0, le=MAX_TURN, description="0-based position of the rated turn in the thread")
    question: str = Field(default="", max_length=500)  # only used if the stored turn cannot be found
    rating: Literal["up", "down"]
    reasons: list[str] = Field(default_factory=list, max_length=REASONS_MAX * 2)
    comment: str = Field(default="", max_length=COMMENT_MAX)


class FeedbackController:
    """POST /api/feedback, GET /api/threads/{id}/feedback: thumbs on answers. Recording only; nothing reads it back into the model."""

    def __init__(self, container: Container) -> None:
        self._c = container
        self.router = APIRouter(prefix="/api", tags=["feedback"])
        self.router.add_api_route("/feedback", self.submit, methods=["POST"])
        self.router.add_api_route("/threads/{thread_id}/feedback", self.ratings, methods=["GET"])

    async def submit(self, body: FeedbackRequest, user: AuthUser = Depends(current_user)) -> dict:
        thread = await run_in_threadpool(self._c.history.get_thread, user.uid, body.thread_id)
        if thread is None:  # also bounds the table: a user can only rate turns of chats that exist
            raise HTTPException(404, "Chat not found.")
        turns = thread["turns"]
        stored = turns[body.turn] if body.turn < len(turns) else None
        if body.question and (stored is None or stored["question"] != body.question):
            # positions shift once a long chat is trimmed: trust the text the user actually rated, and find that turn by it
            stored = next((t for t in reversed(turns) if t["question"] == body.question), None)
        question = stored["question"] if stored else body.question
        if not question:
            raise HTTPException(404, "Turn not found.")
        try:
            await run_in_threadpool(self._c.feedback.put, user.uid, body.thread_id, body.turn, question, body.rating,
                                    clean_reasons(body.reasons), " ".join(body.comment.split()), snapshot(stored["response"] if stored else None))
        except FeedbackCapReached:
            raise HTTPException(429, "Feedback limit reached.") from None
        except Exception:
            log.warning("feedback not stored", exc_info=True)
            raise HTTPException(503, "Could not save feedback right now.") from None
        return {"ok": True}

    async def ratings(self, thread_id: str, user: AuthUser = Depends(current_user)) -> dict:
        if not THREAD_ID.fullmatch(thread_id):
            raise HTTPException(422, "Invalid thread id.")
        try:
            found = await run_in_threadpool(self._c.feedback.ratings, user.uid, thread_id)
        except Exception:
            log.warning("feedback not read", exc_info=True)
            found = {}  # restoring thumb states is cosmetic
        return {"ratings": {str(k): v for k, v in found.items()}}
