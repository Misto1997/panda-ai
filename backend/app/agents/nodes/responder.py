from __future__ import annotations

import time

from app.agents.base import AgentNode, NodeOutput
from app.agents.state import TurnState
from app.core.enums import CacheStatus, LlmTask, NodeName, PromptId, ResponseType, ValueFormat
from app.core.errors import LlmError
from app.llm.base import LlmContext
from app.presentation.narrative import answer_summary
from app.schemas.chat import ChatResult, ResultMeta, TablePayload

LLM_ROWS = 15


class ResponderNode(AgentNode):
    """Builds the user-facing answer: narrative, table, chart, SQL and provenance."""
    name = NodeName.RESPOND

    def run(self, state: TurnState) -> NodeOutput:
        started, cat = time.perf_counter(), self.deps.catalog
        ir, query = state["ir"], state["query"]
        formats = {m: cat.metric(m).format.value for m in ir["metrics"]}
        titles = {m: cat.metric(m).title for m in ir["metrics"]} | {d: cat.dimension(d).title for d in ir["dimensions"]} | {"date": "Date"}
        facts = {"columns": query["columns"], "rows": query["rows"], "formats": formats, "titles": titles}
        text = self._narrate(state["question"], facts)
        result = ChatResult(
            type=ResponseType.ANSWER, text=text, sql=query["sql"],
            table=TablePayload(columns=query["columns"], rows=query["rows"], formats={**formats, "date": ValueFormat.DATE.value}, titles=titles,
                               truncated=len(query["rows"]) >= self.deps.settings.max_rows),
            chart=self.deps.charts.build(query["columns"], query["rows"]),
            meta=ResultMeta(route="qna", engine=self.deps.query_service.engine.name, llm=self.deps.llm.name, sources=query["sources"],
                            elapsed_ms=query["elapsed_ms"], cache=CacheStatus(query["cache"]), ir_source=state.get("ir_source"),
                            period=query["period"], rows=len(query["rows"]), docs=state.get("docs", [])))
        return NodeOutput({"response": result.to_state(), "last_ir": ir}, [self.step("answer + chart", started, name="respond")])

    def _narrate(self, question: str, facts: dict) -> str:
        prompt = self.deps.prompts.render(PromptId.ANSWER, question=question, columns=facts["columns"], rows=facts["rows"][:LLM_ROWS])
        try:
            return self.deps.llm.text(prompt, context=LlmContext(question=question, task=LlmTask.ANSWER, payload=facts))
        except LlmError as e:  # degrade gracefully: the data is still correct without the prose
            self.log.warning("narration failed, using deterministic summary: %s", e)
            return answer_summary(**facts)
