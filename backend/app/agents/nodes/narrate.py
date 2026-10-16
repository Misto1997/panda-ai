from __future__ import annotations

import hashlib
import json
import time

from app.agents.base import AgentNode, NodeOutput
from app.agents.state import TurnState
from app.core.enums import LlmTask, ModelTier, NodeName, PromptId, ResponseType, ValueFormat
from app.core.errors import PandaError
from app.llm.base import LlmContext
from app.core.logging import get_logger

NARRATED_ROWS = 15
log = get_logger("agent.narrate")


class NarrateNode(AgentNode):
    """Optional model-written prose, run AFTER the data is already on the user's screen. If the model is slow, busy or down the user keeps the
    deterministic summary; this node can never replace a good response with an error."""
    name = NodeName.NARRATE

    def run(self, state: TurnState) -> NodeOutput:
        resp = state.get("response")
        if not self.deps.settings.narrate_enabled or not resp or resp.get("type") not in (ResponseType.ANSWER, ResponseType.RCA):
            return NodeOutput()
        table = resp.get("table")
        if resp["type"] == ResponseType.ANSWER and (not table or len(table["rows"]) <= 1):
            return NodeOutput()  # a single figure is already stated exactly by the summary
        started, use_cache = time.perf_counter(), not state.get("options", {}).get("bypass_cache")
        key = "narr|" + hashlib.sha1(json.dumps([resp["type"], state["question"], table, resp.get("rca")], default=str, sort_keys=True).encode()).hexdigest()
        cached = self.deps.cache.get_result(key) if use_cache else None
        if cached:
            return self._upgraded(resp, cached["text"], started, "from cache")
        try:
            text = self._write(state["question"], resp)
        except PandaError as e:
            self.log.warning("narration skipped: %s", e.details.get("cause") or e.message)
            return NodeOutput({}, [self.step("kept the standard summary (model unavailable)", started)])
        if use_cache:
            self.deps.cache.put_result(key, {"text": text})
        return self._upgraded(resp, text, started, "written by the model")

    def _write(self, question: str, resp: dict) -> str:
        if resp["type"] == ResponseType.RCA:
            prompt = self.deps.prompts.render(PromptId.RCA_NARRATIVE, facts=resp["rca"])
            ctx = LlmContext(task=LlmTask.RCA_NARRATIVE, payload={"facts": resp["rca"]})
        else:
            t = resp["table"]
            formats = {c: f for c, f in t["formats"].items() if f != ValueFormat.DATE.value}  # date columns are labels, not figures to format
            prompt = self.deps.prompts.render(PromptId.ANSWER, question=question, columns=t["columns"], rows=t["rows"][:NARRATED_ROWS], formats=formats)
            ctx = LlmContext(question=question, task=LlmTask.ANSWER, payload={"columns": t["columns"], "rows": t["rows"], "formats": formats, "titles": t["titles"]})
        return self.deps.llm.text(prompt, ModelTier.NARRATION, ctx)

    def _upgraded(self, resp: dict, text: str, started: float, how: str) -> NodeOutput:
        meta = {**resp.get("meta", {}), "narrated": True}
        return NodeOutput({"response": {**resp, "text": text, "meta": meta}}, [self.step(f"insights {how}", started)])

    def _fail(self, message: str, started: float, error: Exception) -> dict:
        self.log.warning("narrate failed, keeping the summary: %s", error)
        return {"trace": []}  # never touch `response`
