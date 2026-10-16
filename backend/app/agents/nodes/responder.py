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
DATE_COLUMN = "date"


class ResponderNode(AgentNode):
    """Builds the user-facing answer: narrative, table, chart, SQL and provenance."""
    name = NodeName.RESPOND

    def run(self, state: TurnState) -> NodeOutput:
        started = time.perf_counter()
        query = state["query"]
        formats, titles = self._describe_columns(query)
        facts = {"columns": query["columns"], "rows": query["rows"], "formats": formats, "titles": titles}
        text = self._narrate(state["question"], facts)
        chart_columns = self._chart_columns(query)
        result = ChatResult(
            type=ResponseType.ANSWER, text=text, sql=query["sql"],
            table=TablePayload(columns=query["columns"], rows=query["rows"], titles=titles, truncated=len(query["rows"]) >= self.deps.settings.max_rows,
                               formats={**formats, **{c: ValueFormat.DATE.value for c in query["date_columns"]}}),
            chart=self.deps.charts.build(chart_columns, query["rows"]),
            meta=ResultMeta(route="qna", engine=self.deps.query_service.engine.name, llm=self.deps.llm.name, sources=query["sources"],
                            elapsed_ms=query["elapsed_ms"], cache=CacheStatus(query["cache"]), ir_source=state.get("ir_source"),
                            period=query["period"], rows=len(query["rows"]), docs=state.get("docs", []), path=state.get("path"),
                            sql_attempts=state.get("sql_attempts"), bytes_processed=query.get("bytes_processed") or state.get("bytes_processed")))
        update = {"response": result.to_state(), "last_ir": state.get("ir"), "last_sql": state.get("sql")}
        return NodeOutput(update, [self.step("answer + chart", started, name="respond")])

    def _describe_columns(self, query: dict) -> tuple[dict[str, str], dict[str, str]]:
        """Display format and title per result column. Columns the semantic layer does not know get a neutral number format."""
        cat, formats, titles = self.deps.catalog, {}, {}
        dim_by_column = {d.column: d for d in cat.dimensions.values()}
        for i, col in enumerate(query["columns"]):
            if col in query["date_columns"] or col == DATE_COLUMN:
                titles[col] = "Date"
            elif col in query["column_metrics"]:
                metric = cat.metric(query["column_metrics"][col])
                formats[col], titles[col] = metric.format.value, metric.title
            elif col in dim_by_column:
                titles[col] = dim_by_column[col].title
            else:
                titles[col] = col.replace("_", " ").title()
                if any(isinstance(r[i], (int, float)) and not isinstance(r[i], bool) for r in query["rows"]):
                    formats[col] = ValueFormat.NUMBER.value
        return formats, titles

    @staticmethod
    def _chart_columns(query: dict) -> list[str]:
        """The chart builder keys on metric ids and `date`; present the model's aliases under those names (rows are positional)."""
        names, used = [], set()
        for col in query["columns"]:
            name = DATE_COLUMN if col in query["date_columns"] else query["column_metrics"].get(col, col)
            names.append(col if name in used else name)
            used.add(name)
        return names

    def _narrate(self, question: str, facts: dict) -> str:
        prompt = self.deps.prompts.render(PromptId.ANSWER, question=question, columns=facts["columns"], rows=facts["rows"][:LLM_ROWS],
                                           formats=facts["formats"])
        try:
            return self.deps.llm.text(prompt, context=LlmContext(question=question, task=LlmTask.ANSWER, payload=facts))
        except LlmError as e:  # degrade gracefully: the data is still correct without the prose
            self.log.warning("narration failed, using deterministic summary: %s", e)
            return answer_summary(**facts)
