from __future__ import annotations

import re

from app.agents.base import AgentNode, NodeOutput
from app.agents.routing import meta_kind
from app.agents.state import TurnState
from app.core.enums import NodeName, ResponseType
from app.core.errors import PandaError
from app.presentation.suggestions import HELP_SUGGESTIONS
from app.schemas.chat import ChatResult, ResultMeta

NOTHING_YET = "I haven't run a query in this chat yet, so there is nothing to show. Ask a question first, for example:"


class MetaNode(AgentNode):
    """Questions about the previous answer ("show me the SQL", "which period did you use") and about the data itself ("till when do you have data").
    Answered from the facts saved with the conversation and from the warehouse date range: no query, no model call."""
    name = NodeName.META
    route_label = "meta"

    def run(self, state: TurnState) -> NodeOutput:
        kind = meta_kind(" ".join(state["question"].lower().split())) or "how"
        facts = state.get("last_facts")
        if kind == "range" or (not facts and kind == "how" and re.search(r"\bdata\b", state["question"].lower())):
            text, sql, meta = self._range(), None, ResultMeta(route="meta", suggestions=list(HELP_SUGGESTIONS))
        elif not facts:
            text, sql, meta = f"{NOTHING_YET}", None, ResultMeta(route="meta", suggestions=list(HELP_SUGGESTIONS))
        else:
            text, sql = self._about(kind, facts)
            meta = ResultMeta(route="meta", period=facts.get("period"), sources=facts.get("sources"), rows=facts.get("rows"), engine=facts.get("engine"),
                              path=facts.get("path"))
        result = ChatResult(type=ResponseType.INFO, text=text, sql=sql, meta=meta)
        return NodeOutput({"response": result.to_state()}, [self.step(f"{kind} (from the previous answer, no query)" if facts else kind)])

    def _range(self) -> str:
        svc = self.deps.query_service
        try:
            first, last = svc.data_range()
        except PandaError:
            return "The data is not loaded right now, so I can't tell its date range. Please try again in a minute."
        r = svc.resolver
        week = r.resolve("last_7_days")
        lines = [f"I have data from **{first}** to **{last}**" if first else f"My data runs through **{last}** (the latest full day)",
                 "It is synthetic Acme Retail data that rolls forward every night, so the last date is always yesterday (UTC).",
                 f"That means **yesterday** is {last} and **last 7 days** is {week.start} to {week.last_day}."]
        return "\n\n".join(lines) + "\n\nTry one of these:"

    @staticmethod
    def _about(kind: str, facts: dict) -> tuple[str, str | None]:
        sql = facts.get("sql") or facts.get("physical_sql")
        asked = facts.get("question") or "your last question"
        bits = [f"period **{facts['period']}**" if facts.get("period") else "", "from " + ", ".join(f"`{t}`" for t in (facts.get("sources") or {}).values())
                if facts.get("sources") else "", f"{facts['rows']} row(s)" if facts.get("rows") is not None else ""]
        detail = ", ".join(b for b in bits if b)
        if facts.get("kind") == "rca":
            head = f"For **{asked}** I ran a root-cause runbook: {detail or 'see the sample queries below'}."
        elif kind == "sql":
            head = f"This is the SQL behind **{asked}**" + (f" ({detail})." if detail else ".")
        else:
            head = f"For **{asked}** I used {detail or 'the governed metrics'}. The SQL is below."
        return head + ("" if sql else "\n\nNo SQL was kept for that answer."), sql
