from __future__ import annotations

import time

from app.core.config import Settings
from app.core.enums import ModelTier
from app.core.errors import LlmError, LlmUnavailableError
from app.core.logging import get_logger
from app.llm.base import AgentMsg, AgentTurn, LlmContext, Prompt, T, ToolCall, ToolSpec
from app.llm.vertex import client_options

log = get_logger("llm.gemini")
BUSY_MESSAGE = "The language model is busy right now. Please try again in a few seconds."
UNAVAILABLE_MESSAGE = "The language model is temporarily unavailable. Please try again in a moment."


class GeminiLlm:
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        from langchain_google_genai import ChatGoogleGenerativeAI

        base = {**client_options(settings), "reasoning_effort": settings.gemini_thinking_level}  # maps to thinking_level in the request

        def client(model: str, timeout: float, retries: int):
            return ChatGoogleGenerativeAI(model=model, timeout=timeout, max_retries=retries, **base)  # provider default sampling

        self._models = {
            ModelTier.FAST: client(settings.gemini_model, settings.llm_timeout_s, settings.llm_max_retries),
            ModelTier.REASONING: client(settings.gemini_pro_model, settings.llm_timeout_s, settings.llm_max_retries),
            ModelTier.NARRATION: client(settings.gemini_model, settings.narration_timeout_s, 0),
        }
        self._trace = settings.trace_payloads

    def structured(self, schema: type[T], prompt: Prompt, context: LlmContext | None = None) -> T:
        started = time.perf_counter()
        try:
            out = self._models[ModelTier.FAST].with_structured_output(schema).invoke(self._messages(prompt))
        except Exception as e:  # provider SDKs raise many types; normalise at the boundary
            raise self._failed(e, f"structured {schema.__name__}", started) from e
        log.info("llm structured %s ok in %.1fs", schema.__name__, time.perf_counter() - started)
        if out is None:
            raise LlmError(f"model returned no structured output for {schema.__name__}")
        if self._trace:
            log.debug("structured %s -> %s", schema.__name__, out)
        return out

    def text(self, prompt: Prompt, tier: ModelTier = ModelTier.FAST, context: LlmContext | None = None) -> str:
        started = time.perf_counter()
        try:
            content = self._models[tier].invoke(self._messages(prompt)).content
        except Exception as e:
            raise self._failed(e, f"text ({tier.value})", started) from e
        log.info("llm text (%s) ok in %.1fs", tier.value, time.perf_counter() - started)
        text = content if isinstance(content, str) else "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
        if not text.strip():
            raise LlmError("model returned an empty response")
        return text

    def agent_step(self, prompt: Prompt, tools: list[ToolSpec], transcript: list[AgentMsg], context: LlmContext | None = None) -> AgentTurn:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        messages: list = [SystemMessage(prompt.system), HumanMessage(prompt.user)]
        for m in transcript:
            if m.role == "assistant":
                messages.append(m.raw if m.raw is not None else AIMessage(content=m.text, tool_calls=[{"id": c.id, "name": c.name, "args": c.args} for c in m.calls]))
            else:
                messages.append(ToolMessage(content=m.text, tool_call_id=m.call_id, name=m.name))
        started = time.perf_counter()
        try:
            reply = self._models[ModelTier.FAST].bind_tools([{"name": t.name, "description": t.description, "parameters": t.args.model_json_schema()} for t in tools]).invoke(messages)
        except Exception as e:
            raise self._failed(e, "agent step", started) from e
        calls = tuple(ToolCall(id=str(c.get("id") or f"call-{i}"), name=c["name"], args=dict(c.get("args") or {})) for i, c in enumerate(reply.tool_calls or []))
        content = reply.content
        text = content if isinstance(content, str) else "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
        log.info("llm agent step ok in %.1fs: %s", time.perf_counter() - started, [c.name for c in calls] or "text")
        return AgentTurn(text=text.strip(), calls=calls, raw=reply)

    @staticmethod
    def _failed(error: Exception, what: str, started: float) -> LlmError:
        """Unparseable output is a plain LlmError (a repair or fallback may help). Anything else is a service problem; the raw provider
        text goes to the log and to `details`, never to the user."""
        from langchain_core.exceptions import OutputParserException

        elapsed = time.perf_counter() - started
        text = str(error)
        log.warning("llm %s failed after %.1fs: %s: %s", what, elapsed, type(error).__name__, text[:300])
        if isinstance(error, (OutputParserException, ValueError)):
            return LlmError(f"{what}: {text}")
        lowered = text.lower()
        limited = "429" in lowered or "resource exhausted" in lowered or "resource_exhausted" in lowered or "quota" in lowered
        return LlmUnavailableError(BUSY_MESSAGE if limited else UNAVAILABLE_MESSAGE,
                                   details={"rate_limited": limited, "cause": f"{type(error).__name__}: {text[:300]}", "elapsed_s": round(elapsed, 1)})

    @staticmethod
    def _messages(prompt: Prompt) -> list[tuple[str, str]]:
        return [("system", prompt.system), ("human", prompt.user)]
