from __future__ import annotations

from app.agents.base import AgentNode, NodeOutput
from app.agents.state import TurnState
from app.core.enums import NodeName, ResponseType
from app.schemas.chat import ChatResult, ResultMeta


class HelpNode(AgentNode):
    name = NodeName.HELP
    route_label = "help"

    def run(self, state: TurnState) -> NodeOutput:
        metrics = ", ".join(f"`{m}`" for m in self.deps.catalog.metrics)
        text = ("I answer questions about Acme Retail from governed metrics. Try:\n"
                "- **Ask**: \"Net GMV by zone last 7 days\", \"daily visits trend by marketplace\"\n"
                "- **Investigate**: \"Why did Net GMV drop in the last 14 days?\"\n"
                "- **Learn**: \"What is ASP?\"\n\n"
                f"Metrics: {metrics}")
        return NodeOutput({"response": ChatResult(type=ResponseType.INFO, text=text, meta=ResultMeta(route="help")).to_state()},
                          [self.step("help")])
