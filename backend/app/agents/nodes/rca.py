from __future__ import annotations

import time

from app.agents.base import AgentNode, NodeOutput
from app.agents.contracts import RcaRequest
from app.agents.state import TurnState
from app.core.enums import DocKind, LlmTask, ModelTier, NodeName, PromptId, ResponseType
from app.core.errors import LlmError, QueryValidationError
from app.llm.base import LlmContext
from app.presentation.narrative import rca_summary
from app.schemas.chat import ChatResult, ResultMeta

RCA_DOC_KINDS = {DocKind.METRIC, DocKind.RCA_TREE}
RCA_CONTEXT_DOCS = 6


class RcaNode(AgentNode):
    """Root-cause analysis: pick metric/period, run the runbook deterministically, let the LLM narrate the facts."""
    name = NodeName.RCA
    route_label = "rca"

    def run(self, state: TurnState) -> NodeOutput:
        started, question = time.perf_counter(), state["question"]
        docs = self.deps.search.search(question, RCA_CONTEXT_DOCS, RCA_DOC_KINDS)
        context = "\n".join(f"[{d.kind.value}] {d.id}: {d.text}" for d in docs)
        ctx = LlmContext(question=question, vocabulary=self.deps.vocabulary, last_intent=state.get("last_ir"))
        request = self.deps.llm.structured(RcaRequest, self.deps.prompts.render(PromptId.RCA_REQUEST, question=question, context=context), ctx)
        if request.metric not in self.deps.catalog.metrics:
            raise QueryValidationError(f"I can't investigate '{request.metric}'. Try Net GMV, visits, ASP or conversion rate.")

        report = self.deps.investigator.investigate(request.metric, request.time_expr)
        facts = report.model_dump(mode="json")
        narrative = self._narrate(facts)
        result = ChatResult(
            type=ResponseType.RCA, text=narrative, rca=facts, sql="\n\n".join(report.sql_sample),
            meta=ResultMeta(route="rca", engine=self.deps.query_service.engine.name, llm=self.deps.llm.name, tree=report.tree,
                            queries=report.queries_run, elapsed_ms=round((time.perf_counter() - started) * 1000, 1), docs=[d.id for d in docs]))
        last_ir = {"metrics": [request.metric], "dimensions": [], "filters": [], "time_expr": request.time_expr, "grain": "none"}
        return NodeOutput({"response": result.to_state(), "last_ir": last_ir},
                          [self.step(f"runbook={report.tree} {report.queries_run} governed queries", started)])

    def _narrate(self, facts: dict) -> str:
        prompt = self.deps.prompts.render(PromptId.RCA_NARRATIVE, facts=facts)
        try:
            return self.deps.llm.text(prompt, ModelTier.REASONING, LlmContext(task=LlmTask.RCA_NARRATIVE, payload={"facts": facts}))
        except LlmError as e:
            self.log.warning("narration failed, using deterministic summary: %s", e)
            return rca_summary(facts)
