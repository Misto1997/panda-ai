"""Rule-based stand-in for the LLM: offline demo fallback and deterministic test double.
It only understands the vocabulary passed in LlmContext, exactly like the real planner."""
from __future__ import annotations

import json
import re

from app.core.enums import Confidence, LlmTask, ModelTier, Route
from app.llm.base import AgentMsg, AgentTurn, LlmContext, Prompt, T, Term, ToolCall, ToolSpec
from app.presentation.narrative import answer_summary, rca_summary

RCA_WORDS = re.compile(r"\b(why|root cause|reason|investigate|rca|what happened|what caused)\b|\b(drop|dropped|decline|declined|fell|fall|dip|dipped|decrease|decreased|rise|rose|spike|spiked|increase|increased)\b")
DISCOVER_WORDS = re.compile(r"\b(what is|what's|define|definition|meaning|what does|which metrics|what metrics|available|glossary|how is .* (calculated|computed))\b")
HELP_WORDS = re.compile(r"^(hi|hello|hey|help)\b|what can you do|how do i use")
DATA_WORDS = re.compile(r"\b(by|per|last|yesterday|trend|top|compare|show|total|how many|how much)\b")
GRAINS = [("day", r"\b(daily|per day|trend|over time|by day|each day)\b"), ("week", r"\b(weekly|by week|per week)\b"),
          ("month", r"\b(monthly|by month|per month)\b")]
TIME_PATTERNS = [(r"\byesterday\b", "yesterday"), (r"\blast week\b|\bprevious week\b", "last_week"), (r"\bthis week\b", "this_week"),
                 (r"\blast month\b", "last_month"), (r"\bthis month\b", "this_month"), (r"\bmtd\b|month to date", "mtd"),
                 (r"\b(past|last) week\b", "last_7_days"), (r"\ball time\b|\bever\b", "all_time"),
                 (r"\blast quarter\b|\b90 days\b", "last_90_days")]


def _mentions(names: list[str], text: str) -> re.Match | None:
    for name in names:
        if m := re.search(rf"\b{re.escape(name.lower())}s?\b", text):
            return m
    return None


class MockLlm:
    name = "mock"

    def structured(self, schema: type[T], prompt: Prompt, context: LlmContext | None = None) -> T:
        ctx = context or LlmContext()
        q = ctx.question.lower()
        builder = {"RcaRequest": self._rca_request, "QueryIR": self._query_ir,
                   "SqlDraft": self._sql_draft}.get(schema.__name__)
        if builder is None:
            raise NotImplementedError(schema.__name__)
        return schema(**builder(q, ctx))

    def agent_step(self, prompt: Prompt, tools: list[ToolSpec], transcript: list[AgentMsg], context: LlmContext | None = None) -> AgentTurn:
        """Offline judge: checks the semantic layer when asked about available data, then routes with the keyword rules."""
        ctx = context or LlmContext()
        q = ctx.question.lower()
        results = [json.loads(m.text) for m in transcript if m.role == "tool"]
        if not results and any(t.name == "search_semantic_layer" for t in tools) and re.search(r"\b(do you have|have data|data on|available for)\b", q):
            return AgentTurn("", (ToolCall("mock-1", "search_semantic_layer", {"query": q}),))
        matches = results[-1].get("matches") if results else None
        if matches is not None and not any(re.sub(r"[^a-z0-9 ]", " ", m["title"].lower()).strip() in q for m in matches):  # nothing it found is what was asked for
            return AgentTurn("", (ToolCall("mock-2", "decide", {"route": "deny", "reply": "I don't have that in my semantic layer."}),))
        route = self._route(q, ctx)["route"]
        decision = {Route.HELP: "deny"}.get(route, route.value)
        return AgentTurn("", (ToolCall("mock-2", "decide", {"route": decision, "reason": "keyword judge (mock)"}),))

    # ---- structured behaviours ----
    @staticmethod
    def _route(q: str, ctx: LlmContext) -> dict:
        if HELP_WORDS.search(q):
            route = Route.HELP
        elif RCA_WORDS.search(q):
            route = Route.RCA
        elif DISCOVER_WORDS.search(q) and not DATA_WORDS.search(q):
            route = Route.DISCOVER
        else:
            route = Route.QNA
        return {"route": route, "reasoning": "keyword router (mock)"}

    def _rca_request(self, q: str, ctx: LlmContext) -> dict:
        metrics = self._metrics(q, ctx.vocabulary.metrics)
        prior = (ctx.last_intent or {}).get("metrics", [])
        return {"metric": metrics[0] if metrics else (prior[0] if prior else "net_gmv"), "time_expr": self._time(q) or "last_14_days"}

    def _query_ir(self, q: str, ctx: LlmContext) -> dict:
        last = ctx.last_intent
        metrics = self._metrics(q, ctx.vocabulary.metrics)
        dims, filters = [], []
        for d in ctx.vocabulary.dimensions:
            values = [v for v in d.values if re.search(rf"\b{re.escape(v.lower())}\b", q)]
            by = re.search(rf"\b(by|per|across|each|breakdown by|split by|for every)\s+(the\s+)?({'|'.join(map(re.escape, [n.lower() for n in d.names]))})s?\b", q)
            if by:
                dims.append(d.id)
            elif values:
                filters.append({"dim": d.id, "values": values, "negate": False})
        grain = next((g for g, pat in GRAINS if re.search(pat, q)), "none")
        follow_up = bool(last) and not metrics
        time_expr = self._time(q) or (last["time_expr"] if follow_up else "last_30_days")
        if follow_up:
            metrics = last["metrics"]
            dims = dims or ([] if re.search(r"\b(overall|total)\b", q) else last["dimensions"])
            filters = filters or last["filters"]
            grain = grain if grain != "none" else last.get("grain", "none")
        top = re.search(r"\btop\s+(\d+)\b", q)
        return {"metrics": metrics, "dimensions": dims, "filters": filters, "time_expr": time_expr, "grain": grain,
                "order_by": metrics[0] if metrics and dims else None,
                "order_desc": not re.search(r"\b(bottom|lowest|worst)\b", q), "limit": int(top.group(1)) if top else None}

    def _sql_draft(self, q: str, ctx: LlmContext) -> dict:
        """Renders the intent it understands as logical SQL, the way a real model is asked to. Repair is a no-op (the mock cannot
        reason about errors), so a rejected draft falls through to the IR fallback."""
        if ctx.task == LlmTask.SQL_REPAIR:
            return {"sql": (ctx.payload or {}).get("sql") or "", "rationale": "mock cannot repair SQL", "confidence": Confidence.LOW}
        ir = self._query_ir(q, ctx)
        if not ir["metrics"] or ctx.render_sql is None:
            return {"sql": "", "rationale": "No metric identified. Ask about a metric such as Net GMV, orders, ASP or visits.",
                    "confidence": Confidence.LOW}
        return {"sql": ctx.render_sql(ir), "rationale": f"mock: {ir['metrics']} by {ir['dimensions']} over {ir['time_expr']}",
                "confidence": Confidence.MEDIUM}

    @staticmethod
    def _metrics(q: str, metrics: list[Term]) -> list[str]:
        found: list[tuple[str, tuple[int, int]]] = []
        for term in sorted(metrics, key=lambda t: -max(len(n) for n in t.names)):  # longest name first so "net gmv" beats "gmv"
            m = _mentions(term.names, q)
            if m and not any(m.start() >= a and m.end() <= b for _, (a, b) in found):
                found.append((term.id, m.span()))
        return [mid for mid, _ in sorted(found, key=lambda x: x[1][0])]

    @staticmethod
    def _time(q: str) -> str | None:
        if m := re.search(r"\b(?:last|past|previous)\s+(\d+)\s+days?\b", q):
            return f"last_{m.group(1)}_days"
        if m := re.search(r"\b(?:last|past)\s+(\d+)\s+weeks?\b", q):
            return f"last_{int(m.group(1)) * 7}_days"
        return next((value for pat, value in TIME_PATTERNS if re.search(pat, q)), None)

    # ---- text behaviours ----
    def text(self, prompt: Prompt, tier: ModelTier = ModelTier.FAST, context: LlmContext | None = None) -> str:
        ctx = context or LlmContext()
        if ctx.task == LlmTask.ANSWER:
            return answer_summary(**ctx.payload)
        if ctx.task == LlmTask.RCA_NARRATIVE:
            return rca_summary(ctx.payload["facts"])
        if ctx.task == LlmTask.DISCOVER:
            return "Here is what the semantic layer says:\n" + "\n".join(f"- **{d['title']}**: {d['text'][:240]}" for d in ctx.payload["docs"][:4])
        return ""
