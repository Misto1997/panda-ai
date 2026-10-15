from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from app.agents.state import TurnOptions


@dataclass
class RunUpdate:
    node: str
    steps: list[dict] = field(default_factory=list)
    response: dict | None = None


class TurnRunner:
    """Runs one conversational turn and yields per-node updates. Shared by the HTTP stream and the CLI."""

    def __init__(self, graph) -> None:
        self._graph = graph

    def stream(self, question: str, thread_id: str, options: TurnOptions) -> Iterator[RunUpdate]:
        config = {"configurable": {"thread_id": thread_id}}
        for chunk in self._graph.stream({"question": question, "options": options}, config, stream_mode="updates"):
            for node, update in chunk.items():
                if update:
                    yield RunUpdate(node, update.get("trace") or [], update.get("response"))
