"""Per-turn cap on model calls. The chat controller opens a budget for each turn; every call made while it is open
(in any worker thread that inherited the context) consumes one unit. No open budget (CLI, bootstrap) means unlimited."""
from __future__ import annotations

import threading
from contextvars import ContextVar

from app.core.enums import ModelTier
from app.core.errors import LlmBudgetExceededError
from app.llm.base import LlmClient, LlmContext, Prompt, T


class TurnLlmBudget:
    def __init__(self, limit: int) -> None:
        self.limit, self.used, self._lock = limit, 0, threading.Lock()

    def consume(self) -> None:
        with self._lock:
            if self.used >= self.limit:
                raise LlmBudgetExceededError("This question needed too many model calls and was stopped. Try a simpler question.")
            self.used += 1


_current: ContextVar[TurnLlmBudget | None] = ContextVar("llm_turn_budget", default=None)


def open_turn_budget(limit: int) -> TurnLlmBudget:
    budget = TurnLlmBudget(limit)
    _current.set(budget)
    return budget


class BudgetedLlm:
    def __init__(self, inner: LlmClient) -> None:
        self._inner, self.name = inner, inner.name

    @staticmethod
    def _charge() -> None:
        if (budget := _current.get()) is not None:
            budget.consume()

    def structured(self, schema: type[T], prompt: Prompt, context: LlmContext | None = None) -> T:
        self._charge()
        return self._inner.structured(schema, prompt, context)

    def text(self, prompt: Prompt, tier: ModelTier = ModelTier.FAST, context: LlmContext | None = None) -> str:
        self._charge()
        return self._inner.text(prompt, tier, context)
