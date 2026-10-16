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
    ir: dict | None           # canonical intent: normalised from the generated SQL, or filled by the LLM on the fallback path
    ir_source: str | None     # IrSource
    docs: list[str]
    sql: str | None           # logical SQL written by the LLM (text-to-sql path); None on the IR fallback path
    path: str | None          # QueryPath
    sql_attempts: int | None  # generation + repair calls
    rationale: str | None
    confidence: str | None
    bytes_processed: int | None
    query: dict | None        # {sql, sources, period, columns, rows, elapsed_ms, cache, column_metrics, date_columns}
    response: dict | None     # ChatResult.to_state()
    last_ir: dict | None      # survives across turns (follow-ups); derived from the generated SQL
    last_sql: str | None      # survives across turns: the previous logical SQL
    last_facts: dict | None   # survives across turns: summary of the previous answer (question, period, sources, SQL) for "show me the SQL" style follow-ups
    reply: str | None         # a ready-made user-facing message chosen by the judge (denials)
    trace: Annotated[list[dict], lambda _old, new: new]  # steps of the node that just ran (replaced, not accumulated)


TURN_RESET: dict = {"ir": None, "ir_source": None, "docs": [], "sql": None, "path": None, "sql_attempts": None, "rationale": None,
                    "confidence": None, "bytes_processed": None, "query": None, "response": None, "reply": None}
