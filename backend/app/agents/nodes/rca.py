from __future__ import annotations

import time

from app.agents.base import AgentNode, NodeOutput
from app.agents.contracts import RcaRequest
from app.agents.state import TurnState
from app.core.enums import DocKind, NodeName, PromptId, ResponseType
from app.core.errors import QueryValidationError
from app.llm.base import LlmContext
from app.query.period import TIME_GRAMMAR, extract_time_expr, normalize_time_expr
from app.presentation.narrative import rca_summary
from app.schemas.chat import ChatResult, ResultMeta

RCA_DOC_KINDS = {DocKind.METRIC, DocKind.RCA_TREE}
RCA_CONTEXT_DOCS = 6
DEFAULT_RCA_PERIOD = "last_14_days"


class RcaNode(AgentNode):
    """Root-cause analysis: pick metric/period, run the runbook deterministically, let the LLM narrate the facts."""
    name = NodeName.RCA
    route_label = "rca"

    def run(self, state: TurnState) -> NodeOutput:
        started, question = time.perf_counter(), state["question"]
        docs = self.deps.search.search(question, RCA_CONTEXT_DOCS, RCA_DOC_KINDS)
        metric, time_expr = self._request(state, docs)
        report = self.deps.investigator.investigate(metric.id, time_expr)
        facts = report.model_dump(mode="json")
        result = ChatResult(
            type=ResponseType.RCA, text=rca_summary(facts), rca=facts, sql="\n\n".join(report.sql_sample),  # NarrateNode may upgrade the prose
            meta=ResultMeta(route="rca", engine=self.deps.query_service.engine.name, llm=self.deps.llm.name, tree=report.tree,
                            queries=report.queries_run, elapsed_ms=round((time.perf_counter() - started) * 1000, 1), docs=[d.id for d in docs]))
        last_ir = {"metrics": [metric.id], "dimensions": [], "filters": [], "time_expr": time_expr, "grain": "none"}
        last_facts = {"question": question, "kind": "rca", "sql": "\n\n".join(report.sql_sample) or None, "period": f"{report.current.start} to {report.current.end}",
                      "rows": None, "engine": self.deps.query_service.engine.name}
        return NodeOutput({"response": result.to_state(), "last_ir": last_ir, "last_sql": None, "last_facts": last_facts},  # an RCA turn invalidates the previous SQL
                          [self.step(f"runbook={report.tree} {report.queries_run} governed queries", started)])

    def _request(self, state: TurnState, docs) -> tuple:
        """Metric and period come from the words of the question (or the previous turn). The model is asked only when neither is there."""
        question, last = state["question"], state.get("last_ir") or {}
        cat = self.deps.catalog
        mentioned = cat.metrics_in(question)
        metric = mentioned[0] if mentioned else (cat.find_metric(last["metrics"][0]) if last.get("metrics") else None)
        expr = extract_time_expr(question)
        if metric is None:  # nothing to go on: ask the model
            context = "\n".join(f"[{d.kind.value}] {d.id}: {d.text}" for d in docs)
            ctx = LlmContext(question=question, vocabulary=self.deps.vocabulary, last_intent=last or None)
            request = self.deps.llm.structured(RcaRequest, self.deps.prompts.render(
                PromptId.RCA_REQUEST, question=question, context=context, metric_ids=", ".join(cat.metrics), time_grammar=TIME_GRAMMAR), ctx)
            metric = cat.find_metric(request.metric)
            expr = expr or normalize_time_expr(request.time_expr)
        if metric is None:
            raise QueryValidationError("Tell me which metric to investigate, for example Net GMV, visits, ASP or conversion rate.")
        return metric, expr or DEFAULT_RCA_PERIOD
