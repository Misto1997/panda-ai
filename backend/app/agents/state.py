from __future__ import annotations

from typing import Annotated, TypedDict


class TurnOptions(TypedDict, total=False):
    force_raw: bool
    bypass_cache: bool


class TurnState(TypedDict, total=False):
    """Checkpointed per conversation thread. Everything must be JSON-serialisable. Only `last_ir` survives across turns."""
    question: str
    options: TurnOptions
    route: str
    ir: dict | None
    ir_source: str | None
    docs: list[str]
    query: dict | None        # {sql, sources, period, columns, rows, elapsed_ms, cache}
    response: dict | None     # ChatResult.to_state()
    last_ir: dict | None
    trace: Annotated[list[dict], lambda _old, new: new]  # steps of the node that just ran (replaced, not accumulated)


TURN_RESET: dict = {"ir": None, "ir_source": None, "docs": [], "query": None, "response": None}
