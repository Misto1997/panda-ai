from __future__ import annotations

import time

from app.agents.base import AgentNode, NodeOutput
from app.agents.state import TurnState
from app.core.enums import NodeName, QueryMode
from app.query.ir import QueryIR


class ExecutorNode(AgentNode):
    """Compiles the intent to governed SQL, validates it, runs it (through the result-layer cache)."""
    name = NodeName.EXECUTE

    def run(self, state: TurnState) -> NodeOutput:
        started = time.perf_counter()
        options = state.get("options", {})
        mode = QueryMode.RAW if options.get("force_raw") else QueryMode.AUTO
        outcome = self.deps.query_service.execute(QueryIR.model_validate(state["ir"]), mode, use_cache=not options.get("bypass_cache"))
        query = {"sql": outcome.compiled.sql, "sources": outcome.compiled.sources,
                 "period": f"{outcome.compiled.period.start} to {outcome.compiled.period.last_day}",
                 "columns": outcome.result.columns, "rows": outcome.result.rows,
                 "elapsed_ms": round(outcome.result.elapsed_ms, 1), "cache": outcome.cache.value}
        engine = self.deps.query_service.engine.name
        return NodeOutput({"query": query}, [
            self.step(f"sources={outcome.compiled.sources} mode={mode.value}", name="compile"),
            self.step(f"{len(outcome.result.rows)} rows on {engine}", started, name="execute", cache=outcome.cache)])


def after_execute(state: TurnState) -> str:
    return "__end__" if state.get("response") else NodeName.RESPOND.value
