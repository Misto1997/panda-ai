"""The judge: an LLM with a few read-only tools that decides what to do with a message the rules could not place. It can check facts
(data range, exact period, what the semantic layer contains, what was asked before), then routes the turn or denies it firmly.
Bounded: at most MAX_STEPS model turns, the last one can only decide."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.agents.deps import NodeDependencies
from app.agents.tools import DECIDE, JudgeTools, route_of
from app.core.enums import PromptId, Route
from app.core.errors import LlmError
from app.core.logging import get_logger
from app.llm.base import AgentMsg, LlmContext, Prompt

log = get_logger("agent.judge")
MAX_STEPS = 3
REPLY_CHARS = 400
PLAIN_REPLY_CHARS = 300


@dataclass
class Judgement:
    route: Route
    reply: str = ""
    tools: list[str] = field(default_factory=list)
    reason: str = ""


class Judge:
    def __init__(self, deps: NodeDependencies) -> None:
        self._deps = deps

    def judge(self, question: str, last_ir: dict | None, last_facts: dict | None) -> Judgement:
        tools = JudgeTools(self._deps, last_facts)
        prompt = self._prompt(question, last_facts)
        ctx = LlmContext(question=question, vocabulary=self._deps.vocabulary, last_intent=last_ir, payload={"last_facts": last_facts})
        transcript: list[AgentMsg] = []
        used: list[str] = []
        for step in range(MAX_STEPS):
            specs = tools.lookups() if step < MAX_STEPS - 1 else tools.decide_only()
            turn = self._deps.llm.agent_step(prompt, specs, transcript, ctx)
            decide = next((c for c in turn.calls if c.name == DECIDE), None)
            if decide is not None:
                return self._decision(decide.args, used)
            if not turn.calls:  # the model answered in prose: show it as a (bounded) denial/clarification rather than guessing a route
                text = re.sub(r"\s+", " ", turn.text).strip()
                if not text:
                    raise LlmError("judge returned neither a decision nor text")
                return Judgement(Route.OFF_TOPIC, text[:PLAIN_REPLY_CHARS], used, "plain reply")
            transcript.append(AgentMsg("assistant", turn.text, turn.calls, raw=turn.raw))
            for call in turn.calls:
                used.append(call.name)
                transcript.append(AgentMsg("tool", tools.run(call), call_id=call.id, name=call.name))
        raise LlmError("judge did not decide")  # unreachable in practice: the last step only offers `decide`

    @staticmethod
    def _decision(args: dict, used: list[str]) -> Judgement:
        try:
            route = route_of(str(args.get("route", "")))
        except KeyError:
            raise LlmError(f"judge chose an unknown route: {args.get('route')!r}") from None
        reply = re.sub(r"\s+", " ", str(args.get("reply") or "")).strip()[:REPLY_CHARS]
        return Judgement(route, reply if route == Route.OFF_TOPIC else "", used, str(args.get("reason") or "")[:200])

    def _prompt(self, question: str, last_facts: dict | None) -> Prompt:
        d = self._deps
        try:
            first, last = d.query_service.data_range()
            span = f"{first or 'earliest'} to {last} inclusive ('yesterday' = {last})"
        except Exception:  # warehouse not reachable: the judge still works from the semantic layer
            span = "unknown right now"
        brief = {k: v for k, v in (last_facts or {}).items() if k in ("question", "period", "kind")} or "none"
        return d.prompts.render(PromptId.JUDGE, question=question, data_range=span, last_facts=brief,
                                metrics=", ".join(f"{m.id} ({m.title})" for m in d.catalog.metrics.values()),
                                dimensions=", ".join(x.id for x in d.catalog.dimensions.values()))
