from __future__ import annotations

import time

from app.agents.base import AgentNode, NodeOutput
from app.agents.state import TurnState
from app.core.enums import LlmTask, NodeName, PromptId, ResponseType
from app.core.errors import LlmError
from app.llm.base import LlmContext
from app.schemas.chat import ChatResult, ResultMeta

DISCOVER_DOCS = 5


class DiscoveryNode(AgentNode):
    """Answers 'what is X / what exists' from retrieved semantic-layer documents only."""
    name = NodeName.DISCOVER
    route_label = "discover"

    def run(self, state: TurnState) -> NodeOutput:
        started, question = time.perf_counter(), state["question"]
        docs = self.deps.search.search(question, DISCOVER_DOCS)
        context = "\n".join(f"[{d.kind.value}] {d.id}: {d.text}" for d in docs)
        payload = {"docs": [{"title": d.title, "text": d.text} for d in docs]}
        try:
            text = self.deps.llm.text(self.deps.prompts.render(PromptId.DISCOVER, question=question, context=context),
                                      context=LlmContext(question=question, task=LlmTask.DISCOVER, payload=payload))
        except LlmError as e:
            self.log.warning("discover narration failed, listing documents: %s", e)
            text = "\n".join(f"- **{d['title']}**: {d['text'][:240]}" for d in payload["docs"])
        result = ChatResult(type=ResponseType.INFO, text=text, meta=ResultMeta(
            route="discover", docs=[d.id for d in docs], llm=self.deps.llm.name, search_backend=self.deps.search.backend_name))
        return NodeOutput({"response": result.to_state()}, [self.step(", ".join(d.id for d in docs), started)])
