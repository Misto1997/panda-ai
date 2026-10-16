from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TypeVar

from pydantic import BaseModel

from app.core.enums import LlmTask, ModelTier

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str


@dataclass(frozen=True)
class Term:
    id: str
    names: list[str]
    values: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Vocabulary:
    metrics: list[Term]
    dimensions: list[Term]


@dataclass(frozen=True)
class LlmContext:
    """Side-channel for the offline mock only. Real models see everything through the Prompt."""
    question: str = ""
    vocabulary: Vocabulary | None = None
    last_intent: dict | None = None
    task: LlmTask | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    render_sql: Callable[[dict], str] | None = None  # QueryIR dict -> logical SQL; lets the mock emit SQL like a real model would


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model may call: a name, a description and a pydantic model for its arguments."""
    name: str
    description: str
    args: type[BaseModel]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class AgentMsg:
    """One entry of a tool-calling transcript. `raw` is the provider's own message object for assistant turns (kept so provider-specific
    state, like Gemini thought signatures, survives the round trip)."""
    role: str                                   # "assistant" | "tool"
    text: str = ""
    calls: tuple[ToolCall, ...] = ()
    call_id: str = ""                           # tool messages: which call this answers
    name: str = ""
    raw: Any = None


@dataclass(frozen=True)
class AgentTurn:
    text: str
    calls: tuple[ToolCall, ...]
    raw: Any = None


class LlmClient(Protocol):
    name: str

    def structured(self, schema: type[T], prompt: Prompt, context: LlmContext | None = None) -> T: ...
    def text(self, prompt: Prompt, tier: ModelTier = ModelTier.FAST, context: LlmContext | None = None) -> str: ...
    def agent_step(self, prompt: Prompt, tools: list[ToolSpec], transcript: list[AgentMsg], context: LlmContext | None = None) -> AgentTurn:
        """One model turn of a tool-calling loop: the model answers with text and/or tool calls. The caller runs the tools and appends results."""
