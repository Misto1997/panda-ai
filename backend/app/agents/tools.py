"""Tools the judge agent may call. Each is a small, read-only, bounded function over the same services the nodes use, so the model
checks facts (data range, periods, what the semantic layer contains, what was asked before) instead of guessing them."""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.deps import NodeDependencies
from app.core.enums import DocKind, Route
from app.core.errors import PandaError
from app.llm.base import ToolCall, ToolSpec

SEARCH_HITS = 5
TEXT_CHARS = 200
DECIDE = "decide"


class NoArgs(BaseModel):
    pass


class ResolvePeriodArgs(BaseModel):
    expression: str = Field(description="A relative period such as yesterday, last_7_days, last_week, this_month, mtd, last_month, or a range YYYY-MM-DD..YYYY-MM-DD")


class SearchArgs(BaseModel):
    query: str = Field(description="What to look for, for example 'returns' or 'conversion rate'")
    kind: Literal["metric", "dimension", "glossary", "any"] = "any"


class DecideArgs(BaseModel):
    route: Literal["qna", "rca", "discover", "meta", "deny"] = Field(
        description="qna: data question answerable now. rca: why a metric moved. discover: what a metric/term means or what exists. "
                    "meta: about the previous answer or the data coverage. deny: cannot or must not be answered.")
    reply: str = Field(default="", description="Only for deny: one or two firm, polite sentences saying why and what IS available. Never invent facts.")
    reason: str = Field(default="", description="Short internal reason")


KINDS = {"metric": {DocKind.METRIC}, "dimension": {DocKind.DIMENSION}, "glossary": {DocKind.GLOSSARY}}


class JudgeTools:
    """Specs for the model plus their implementation. `last_facts` is the previous query summary kept in the conversation state."""

    def __init__(self, deps: NodeDependencies, last_facts: dict | None) -> None:
        self._deps, self._last = deps, last_facts
        self.specs = {
            "data_range": ToolSpec("data_range", "Earliest and latest date loaded in the warehouse, and what 'yesterday' means.", NoArgs),
            "resolve_period": ToolSpec("resolve_period", "Turn a relative period into exact start and end dates against the loaded data.", ResolvePeriodArgs),
            "search_semantic_layer": ToolSpec("search_semantic_layer", "Check whether a metric, dimension or term exists in the governed semantic layer.", SearchArgs),
            "last_query": ToolSpec(
                "last_query", "What the previous answer in this conversation was (question, period, SQL), if any.", NoArgs),
            DECIDE: ToolSpec(DECIDE, "Finish: choose the route (or deny).", DecideArgs),
        }

    def lookups(self) -> list[ToolSpec]:
        return list(self.specs.values())

    def decide_only(self) -> list[ToolSpec]:
        return [self.specs[DECIDE]]

    def run(self, call: ToolCall) -> str:
        """Execute one lookup and return compact JSON. Errors come back as data so the model can react; they never raise."""
        try:
            out = getattr(self, f"_{call.name}")(**call.args) if call.name in self.specs and call.name != DECIDE else {"error": f"unknown tool {call.name}"}
        except (PandaError, TypeError, ValueError) as e:
            out = {"error": str(getattr(e, "message", e))[:200]}
        return json.dumps(out, default=str)

    # ---- implementations ----
    def _data_range(self) -> dict[str, Any]:
        first, last = self._deps.query_service.data_range()
        return {"first_date": first, "last_date": last, "yesterday": last, "note": "data is synthetic and rolls forward nightly"}

    def _resolve_period(self, expression: str) -> dict[str, Any]:
        p = self._deps.query_service.resolver.resolve(expression)
        first, last = self._deps.query_service.data_range()
        inside = (first is None or p.last_day >= first) and p.start <= last
        return {"start": p.start, "end_inclusive": p.last_day, "inside_loaded_data": inside}

    def _search_semantic_layer(self, query: str, kind: str = "any") -> dict[str, Any]:
        docs = self._deps.search.search(query, SEARCH_HITS, KINDS.get(kind))
        return {"matches": [{"id": d.id, "kind": d.kind.value, "title": d.title, "text": d.text[:TEXT_CHARS]} for d in docs]}

    def _last_query(self) -> dict[str, Any]:
        return self._last or {"none": "no query has been run in this conversation yet"}


def route_of(decision: str) -> Route:
    return {"qna": Route.QNA, "rca": Route.RCA, "discover": Route.DISCOVER, "meta": Route.META, "deny": Route.OFF_TOPIC}[decision]
