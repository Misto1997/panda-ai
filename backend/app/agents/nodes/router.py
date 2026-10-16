from __future__ import annotations

import time

from app.agents.base import AgentNode, NodeOutput
from app.agents.judge import Judge
from app.agents.routing import RuleRouter
from app.agents.state import TURN_RESET, TurnState
from app.core.enums import NodeName, Route
from app.core.errors import LlmError, LlmUnavailableError


class RouterNode(AgentNode):
    """Classifies the request and resets per-turn state."""
    name = NodeName.ROUTE

    def __init__(self, deps) -> None:
        super().__init__(deps)
        self._rules = RuleRouter(deps.vocabulary)
        self._judge = Judge(deps)

    def run(self, state: TurnState) -> NodeOutput:
        started = time.perf_counter()
        question = state["question"]
        route, via, reply = self._rules.route(question, has_context=bool(state.get("last_ir"))), "rules", ""
        if route is None:  # the rules cannot place it: the judge (a model with a few read-only tools) decides, or denies
            try:
                verdict = self._judge.judge(question, state.get("last_ir"), state.get("last_facts"))
                route, reply = verdict.route, verdict.reply
                via = "judge" + (f", checked {', '.join(dict.fromkeys(verdict.tools))}" if verdict.tools else "")
                self.log.debug("judge route=%s tools=%s reason=%s", route, verdict.tools, verdict.reason)
            except LlmUnavailableError:
                raise  # the model service itself is failing: tell the user instead of guessing
            except LlmError as e:  # unusable judge output: the SQL planner can still answer or decline
                self.log.warning("judge output unusable, treating as a data question: %s", e)
                route, via = Route.QNA, "judge unusable, defaulting to qna"
        return NodeOutput({**TURN_RESET, "route": route.value, "reply": reply or None}, [self.step(f"{route.value} ({via})", started)])


def after_route(state: TurnState) -> str:
    if state.get("response"):  # the router itself failed
        return "__end__"
    return {Route.QNA: NodeName.PLAN, Route.RCA: NodeName.RCA, Route.DISCOVER: NodeName.DISCOVER,
            Route.HELP: NodeName.HELP, Route.OFF_TOPIC: NodeName.HELP, Route.META: NodeName.META}[Route(state["route"])].value
