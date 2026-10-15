from __future__ import annotations

from app.core.config import Settings
from app.core.enums import ModelTier
from app.core.errors import LlmError
from app.core.logging import get_logger
from app.llm.base import LlmContext, Prompt, T

log = get_logger("llm.gemini")


class GeminiLlm:
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        from langchain_google_genai import ChatGoogleGenerativeAI

        common = {"timeout": settings.llm_timeout_s, "max_retries": settings.llm_max_retries}
        self._models = {
            ModelTier.FAST: ChatGoogleGenerativeAI(model=settings.gemini_model, temperature=0, **common),
            ModelTier.REASONING: ChatGoogleGenerativeAI(model=settings.gemini_pro_model, temperature=0.2, **common),
        }
        self._trace = settings.trace_payloads

    def structured(self, schema: type[T], prompt: Prompt, context: LlmContext | None = None) -> T:
        try:
            out = self._models[ModelTier.FAST].with_structured_output(schema).invoke(self._messages(prompt))
        except Exception as e:  # provider SDKs raise many types; normalise at the boundary
            raise LlmError(f"structured call failed ({schema.__name__}): {e}") from e
        if out is None:
            raise LlmError(f"model returned no structured output for {schema.__name__}")
        if self._trace:
            log.debug("structured %s -> %s", schema.__name__, out)
        return out

    def text(self, prompt: Prompt, tier: ModelTier = ModelTier.FAST, context: LlmContext | None = None) -> str:
        try:
            content = self._models[tier].invoke(self._messages(prompt)).content
        except Exception as e:
            raise LlmError(f"text call failed: {e}") from e
        text = content if isinstance(content, str) else "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
        if not text.strip():
            raise LlmError("model returned an empty response")
        return text

    @staticmethod
    def _messages(prompt: Prompt) -> list[tuple[str, str]]:
        return [("system", prompt.system), ("human", prompt.user)]
