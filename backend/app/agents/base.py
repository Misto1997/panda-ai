"""Template Method base for graph nodes: every node gets timing, logging and uniform error handling for free."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from app.agents.deps import NodeDependencies
from app.agents.state import TurnState
from app.core.enums import CacheStatus, NodeName
from app.core.errors import PandaError
from app.core.logging import get_logger
from app.schemas.chat import ChatResult, StepEvent

GENERIC_ERROR = "Something went wrong while answering that. Please try again."


@dataclass
class NodeOutput:
    update: dict = field(default_factory=dict)
    steps: list[StepEvent] = field(default_factory=list)


class AgentNode(ABC):
    name: ClassVar[NodeName]
    route_label: ClassVar[str] = "qna"  # which user-facing route an error should be attributed to

    def __init__(self, deps: NodeDependencies) -> None:
        self.deps = deps
        self.log = get_logger(f"agent.{self.name.value}")

    @abstractmethod
    def run(self, state: TurnState) -> NodeOutput:
        """Do the node's work. Raise PandaError subclasses for expected failures."""

    def __call__(self, state: TurnState) -> dict:
        started = time.perf_counter()
        try:
            out = self.run(state)
        except PandaError as e:
            return self._fail(e.message if e.user_facing else GENERIC_ERROR, started, e)
        except Exception as e:  # last line of defence: the stream must end with a result, not a stack trace
            return self._fail(GENERIC_ERROR, started, e)
        self.log.debug("%s finished in %.1f ms", self.name.value, (time.perf_counter() - started) * 1000)
        return {**out.update, "trace": [s.model_dump(mode="json", exclude_none=True) for s in out.steps]}

    def _fail(self, message: str, started: float, error: Exception) -> dict:
        if isinstance(error, PandaError) and error.user_facing:
            self.log.info("request rejected: %s", error)
        else:
            self.log.exception("node failed: %s", error)
        step = StepEvent(node=self.name.value, step=self.name.value, detail=f"failed: {message}", ms=_ms(started))
        return {"response": ChatResult.error(message, self.route_label).to_state(), "trace": [step.model_dump(mode="json", exclude_none=True)]}

    def step(self, detail: str, started: float | None = None, name: str | None = None, cache: CacheStatus | None = None) -> StepEvent:
        return StepEvent(node=self.name.value, step=name or self.name.value, detail=detail, ms=_ms(started) if started else 0.0, cache=cache)


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
