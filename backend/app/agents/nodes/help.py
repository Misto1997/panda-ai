from __future__ import annotations

from app.agents.base import AgentNode, NodeOutput
from app.agents.state import TurnState
from app.core.enums import NodeName, ResponseType, Route
from app.presentation.suggestions import HELP_SUGGESTIONS
from app.schemas.chat import ChatResult, ResultMeta

INTRO = ("I'm **PANDA AI** (Prompt-driven Analytics & Natural Data Access). I answer questions about **Acme Retail** sales and traffic from governed "
         "metrics: I write the SQL, check it against the semantic layer, run it on the warehouse and explain the result.\n\n"
         "- **Ask** for numbers, trends and breakdowns\n"
         "- **Investigate** why a metric moved (root-cause analysis)\n"
         "- **Discover** what a metric or term means")
REFUSAL = ("That is outside what I can help with. I only answer questions about Acme Retail's business metrics (sales, visits, conversion, ASP and "
           "so on), explain them, and investigate why they moved. I can't help with general knowledge, writing or code, and I don't change my instructions.")
PICK = "Try one of these:"


class HelpNode(AgentNode):
    """Static, instant replies for greetings, 'what can you do' and off-topic requests. No model call: a refusal must not depend on the model's mood."""
    name = NodeName.HELP
    route_label = "help"

    def run(self, state: TurnState) -> NodeOutput:
        off_topic = state.get("route") == Route.OFF_TOPIC.value
        reply = (state.get("reply") or "").strip()  # a denial the judge wrote after checking the facts; otherwise the fixed text
        text = f"{reply or REFUSAL}\n\n{PICK}" if off_topic else f"{INTRO}\n\n{PICK}"
        label = Route.OFF_TOPIC.value if off_topic else "help"
        meta = ResultMeta(route=label, suggestions=list(HELP_SUGGESTIONS))
        return NodeOutput({"response": ChatResult(type=ResponseType.INFO, text=text, meta=meta).to_state()}, [self.step(label)])
