from __future__ import annotations

import time

from app.agents.base import AgentNode, NodeOutput
from app.agents.state import TurnState
from app.core.enums import NodeName, QueryMode, TimeGrain
from app.query.ir import QueryIR
from app.query.period import Period


class ExecutorNode(AgentNode):
    """Runs the plan: model-written SQL is rewritten to physical tables and guarded; the IR fallback is compiled from governed
    definitions. Both go through the result-layer cache."""
    name = NodeName.EXECUTE

    def run(self, state: TurnState) -> NodeOutput:
        started = time.perf_counter()
        options = state.get("options", {})
        mode = QueryMode.RAW if options.get("force_raw") else QueryMode.AUTO
        use_cache = not options.get("bypass_cache")
        svc = self.deps.query_service
        if state.get("sql"):
            prepared = svc.prepare_sql(state["sql"], mode)
            outcome = svc.execute_sql(prepared, use_cache)
            intent = prepared.intent
            query = {"sql": prepared.physical_sql, "sources": prepared.sources, "period": _period(intent.period),
                     "column_metrics": intent.column_metrics, "date_columns": intent.date_columns}
            compile_step = self.step(f"sources={prepared.sources} mode={mode.value}", name="compile")
        else:
            ir = QueryIR.model_validate(state["ir"])
            outcome = svc.execute(ir, mode, use_cache=use_cache)
            query = {"sql": outcome.compiled.sql, "sources": outcome.compiled.sources, "period": _period(outcome.compiled.period),
                     "column_metrics": {m: m for m in ir.metrics}, "date_columns": ["date"] if ir.grain != TimeGrain.NONE else []}
            compile_step = self.step(f"sources={outcome.compiled.sources} mode={mode.value}", name="compile")
        result = outcome.result
        query |= {"columns": result.columns, "rows": result.rows, "elapsed_ms": round(result.elapsed_ms, 1), "cache": outcome.cache.value,
                  "bytes_processed": result.stats.get("bytes_processed")}
        return NodeOutput({"query": query}, [
            compile_step, self.step(f"{len(result.rows)} rows on {svc.engine.name}", started, name="execute", cache=outcome.cache)])


def _period(period: Period | None) -> str | None:
    return f"{period.start} to {period.last_day}" if period else None


def after_execute(state: TurnState) -> str:
    return "__end__" if state.get("response") else NodeName.RESPOND.value
