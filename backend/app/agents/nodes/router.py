from __future__ import annotations

import time

from app.agents.base import AgentNode, NodeOutput
from app.agents.contracts import RouteDecision
from app.agents.state import TURN_RESET, TurnState
from app.core.enums import NodeName, PromptId, Route
from app.llm.base import LlmContext


class RouterNode(AgentNode):
    """Classifies the request and resets per-turn state."""
    name = NodeName.ROUTE

    def run(self, state: TurnState) -> NodeOutput:
        started = time.perf_counter()
        question = state["question"]
        prompt = self.deps.prompts.render(PromptId.ROUTE, question=question)
        ctx = LlmContext(question=question, vocabulary=self.deps.vocabulary, last_intent=state.get("last_ir"))
        decision = self.deps.llm.structured(RouteDecision, prompt, ctx)
        self.log.debug("route=%s reasoning=%s", decision.route, decision.reasoning)
        return NodeOutput({**TURN_RESET, "route": decision.route.value}, [self.step(decision.route.value, started)])


def after_route(state: TurnState) -> str:
    if state.get("response"):  # the router itself failed
        return "__end__"
    return {Route.QNA: NodeName.PLAN, Route.RCA: NodeName.RCA, Route.DISCOVER: NodeName.DISCOVER,
            Route.HELP: NodeName.HELP}[Route(state["route"])].value
