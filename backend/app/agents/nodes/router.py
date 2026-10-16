from __future__ import annotations

import time

from app.agents.base import AgentNode, NodeOutput
from app.agents.contracts import RouteDecision
from app.agents.routing import RuleRouter
from app.agents.state import TURN_RESET, TurnState
from app.core.enums import NodeName, PromptId, Route
from app.llm.base import LlmContext


class RouterNode(AgentNode):
    """Classifies the request and resets per-turn state."""
    name = NodeName.ROUTE

    def __init__(self, deps) -> None:
        super().__init__(deps)
        self._rules = RuleRouter(deps.vocabulary)

    def run(self, state: TurnState) -> NodeOutput:
        started = time.perf_counter()
        question = state["question"]
        route, via = self._rules.route(question, has_context=bool(state.get("last_ir"))), "rules"
        if route is None:  # ambiguous: only now spend a model call
            prompt = self.deps.prompts.render(PromptId.ROUTE, question=question)
            ctx = LlmContext(question=question, vocabulary=self.deps.vocabulary, last_intent=state.get("last_ir"))
            decision = self.deps.llm.structured(RouteDecision, prompt, ctx)
            route, via = decision.route, "model"
            self.log.debug("route=%s reasoning=%s", route, decision.reasoning)
        return NodeOutput({**TURN_RESET, "route": route.value}, [self.step(f"{route.value} ({via})", started)])


def after_route(state: TurnState) -> str:
    if state.get("response"):  # the router itself failed
        return "__end__"
    return {Route.QNA: NodeName.PLAN, Route.RCA: NodeName.RCA, Route.DISCOVER: NodeName.DISCOVER,
            Route.HELP: NodeName.HELP, Route.OFF_TOPIC: NodeName.HELP}[Route(state["route"])].value
