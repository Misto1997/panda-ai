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


class LlmClient(Protocol):
    name: str

    def structured(self, schema: type[T], prompt: Prompt, context: LlmContext | None = None) -> T: ...
    def text(self, prompt: Prompt, tier: ModelTier = ModelTier.FAST, context: LlmContext | None = None) -> str: ...
