"""AG-UI event models (https://docs.ag-ui.com/concepts/events). Wire format: camelCase fields, SCREAMING_SNAKE `type`.
Only the events PANDA emits are modelled. Frontend mirror: frontend/lib/types.ts."""
from __future__ import annotations

import re
import time
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.core.enums import ActivityType, CustomEventName, EventType, MessageRole, RunOutcome


class AgUiEvent(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    type: EventType
    timestamp: int | None = None  # epoch milliseconds

    def to_wire(self) -> dict:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


class RunStarted(AgUiEvent):
    type: EventType = EventType.RUN_STARTED
    thread_id: str
    run_id: str


class RunFinished(AgUiEvent):
    type: EventType = EventType.RUN_FINISHED
    thread_id: str
    run_id: str
    outcome: dict[str, Any] | None = None
    result: Any | None = None


class RunError(AgUiEvent):
    type: EventType = EventType.RUN_ERROR
    message: str
    code: str | None = None


class StepStarted(AgUiEvent):
    type: EventType = EventType.STEP_STARTED
    step_name: str


class StepFinished(AgUiEvent):
    type: EventType = EventType.STEP_FINISHED
    step_name: str


class TextMessageStart(AgUiEvent):
    type: EventType = EventType.TEXT_MESSAGE_START
    message_id: str
    role: MessageRole = MessageRole.ASSISTANT


class TextMessageContent(AgUiEvent):
    type: EventType = EventType.TEXT_MESSAGE_CONTENT
    message_id: str
    delta: str


class TextMessageEnd(AgUiEvent):
    type: EventType = EventType.TEXT_MESSAGE_END
    message_id: str


class ActivitySnapshot(AgUiEvent):
    type: EventType = EventType.ACTIVITY_SNAPSHOT
    message_id: str
    activity_type: ActivityType
    content: Any
    replace: bool | None = None


class Custom(AgUiEvent):
    type: EventType = EventType.CUSTOM
    name: CustomEventName
    value: Any


def _now() -> int:
    return int(time.time() * 1000)


def chunk_text(text: str, size: int = 48) -> list[str]:
    """Split into ~`size`-char deltas on word boundaries (lossless: ''.join(chunks) == text) so the answer streams."""
    chunks, cur = [], ""
    for token in re.findall(r"\S+\s*|\s+", text):
        if cur and len(cur) + len(token) > size:
            chunks.append(cur)
            cur = ""
        cur += token
    if cur:
        chunks.append(cur)
    return chunks


class AgUiEvents:
    """Builders that stamp timestamps and keep message ids consistent for one run."""

    def __init__(self, thread_id: str, run_id: str) -> None:
        self.thread_id, self.run_id = thread_id, run_id
        self._open: set[str] = set()
        self._closed: set[str] = set()

    def run_started(self) -> RunStarted:
        return RunStarted(thread_id=self.thread_id, run_id=self.run_id, timestamp=_now())

    def run_finished(self, result: Any | None = None) -> RunFinished:
        return RunFinished(thread_id=self.thread_id, run_id=self.run_id, outcome={"type": RunOutcome.SUCCESS.value},
                           result=result, timestamp=_now())

    @staticmethod
    def run_error(message: str, code: str | None = None) -> RunError:
        return RunError(message=message, code=code, timestamp=_now())

    def step_running(self, node: str) -> list[AgUiEvent]:
        """A node has begun: STEP_STARTED plus a panda.step marked running (its finished record follows)."""
        self._open.add(node)
        return [StepStarted(step_name=node, timestamp=_now()),
                Custom(name=CustomEventName.STEP, value={"node": node, "step": node, "detail": "", "ms": 0, "status": "running"}, timestamp=_now())]

    def step(self, step: dict) -> list[AgUiEvent]:
        """A finished trace record. STEP_STARTED/FINISHED are per node (a node may report several records, only the first closes it);
        the panda.step CUSTOM event carries every record's detail."""
        node, events = str(step["node"]), []
        if node not in self._open and node not in self._closed:
            events.append(StepStarted(step_name=node, timestamp=_now()))
            self._open.add(node)
        if node in self._open:
            events.append(StepFinished(step_name=node, timestamp=_now()))
            self._open.discard(node)
            self._closed.add(node)
        return [*events, Custom(name=CustomEventName.STEP, value=step, timestamp=_now())]

    def step_skipped(self, node: str) -> list[AgUiEvent]:
        """A node finished without reporting anything (for example narration that was not needed): close it quietly."""
        out: list[AgUiEvent] = []
        if node in self._open:
            out.append(StepFinished(step_name=node, timestamp=_now()))
            self._open.discard(node)
            self._closed.add(node)
        out.append(Custom(name=CustomEventName.STEP, value={"node": node, "step": node, "detail": "", "ms": 0, "status": "skipped"}, timestamp=_now()))
        return out

    @staticmethod
    def text_message(text: str) -> list[AgUiEvent]:
        mid = uuid.uuid4().hex[:12]
        return [TextMessageStart(message_id=mid, timestamp=_now()),
                *[TextMessageContent(message_id=mid, delta=d, timestamp=_now()) for d in chunk_text(text)],
                TextMessageEnd(message_id=mid, timestamp=_now())]

    @staticmethod
    def surface(messages: list[dict], surface_id: str) -> ActivitySnapshot:
        return ActivitySnapshot(message_id=surface_id, activity_type=ActivityType.A2UI_SURFACE, content=messages,
                                replace=True, timestamp=_now())

    @staticmethod
    def result(payload: dict) -> Custom:
        return Custom(name=CustomEventName.RESULT, value=payload, timestamp=_now())
