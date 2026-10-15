from __future__ import annotations

import time

from app.agents.base import AgentNode, NodeOutput
from app.agents.state import TurnState
from app.core.enums import CacheStatus, DocKind, NodeName, PromptId
from app.llm.base import LlmContext
from app.query.ir import QueryIR

PLAN_DOC_KINDS = {DocKind.METRIC, DocKind.DIMENSION, DocKind.GLOSSARY}
PLAN_CONTEXT_DOCS = 8


class PlannerNode(AgentNode):
    """Retrieves semantic context and asks the LLM for a QueryIR (never SQL). Plan-layer cache skips the LLM."""
    name = NodeName.PLAN

    def run(self, state: TurnState) -> NodeOutput:
        started, question = time.perf_counter(), state["question"]
        use_cache = not state.get("options", {}).get("bypass_cache")
        prior = (state.get("last_ir") or {}).get("metrics", [])
        key = self.deps.cache.plan_key(question, prior)

        if use_cache and (hit := self.deps.cache.get_plan(key)):
            return NodeOutput({"ir": hit["ir"], "docs": hit["docs"], "ir_source": "cache"},
                              [self.step("intent from semantic cache (LLM skipped)", started, cache=CacheStatus.HIT)])

        docs = self.deps.search.search(question, PLAN_CONTEXT_DOCS, PLAN_DOC_KINDS)
        context = "\n".join(f"[{d.kind.value}] {d.id}: {d.text}" for d in docs)
        prompt = self.deps.prompts.render(PromptId.PLAN, question=question, context=context, last_intent=state.get("last_ir"))
        ir = self.deps.llm.structured(QueryIR, prompt, LlmContext(question=question, vocabulary=self.deps.vocabulary, last_intent=state.get("last_ir")))
        doc_ids = [d.id for d in docs]
        if use_cache and ir.metrics:  # never cache a failed plan
            self.deps.cache.put_plan(key, {"ir": ir.model_dump(mode="json"), "docs": doc_ids})
        steps = [self.step(f"{self.deps.search.backend_name}: {', '.join(doc_ids[:6])}", name="retrieve"),
                 self.step(f"metrics={ir.metrics} dims={ir.dimensions} time={ir.time_expr}", started, name="plan")]
        return NodeOutput({"ir": ir.model_dump(mode="json"), "docs": doc_ids, "ir_source": "llm"}, steps)
