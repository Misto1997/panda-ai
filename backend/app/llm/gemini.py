from __future__ import annotations

from app.core.config import Settings
from app.core.enums import ModelTier
from app.core.errors import LlmError, LlmUnavailableError
from app.core.logging import get_logger
from app.llm.base import LlmContext, Prompt, T
from app.llm.vertex import client_options

log = get_logger("llm.gemini")


class GeminiLlm:
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        from langchain_google_genai import ChatGoogleGenerativeAI

        common = {"timeout": settings.llm_timeout_s, "max_retries": settings.llm_max_retries, **client_options(settings)}
        self._models = {
            ModelTier.FAST: ChatGoogleGenerativeAI(model=settings.gemini_model, **common),
            ModelTier.REASONING: ChatGoogleGenerativeAI(model=settings.gemini_pro_model, **common)  # provider default sampling: Gemini 3 degrades at low temperature,
        }
        self._trace = settings.trace_payloads

    def structured(self, schema: type[T], prompt: Prompt, context: LlmContext | None = None) -> T:
        try:
            out = self._models[ModelTier.FAST].with_structured_output(schema).invoke(self._messages(prompt))
        except Exception as e:  # provider SDKs raise many types; normalise at the boundary
            raise self._classify(e, f"structured call failed ({schema.__name__})") from e
        if out is None:
            raise LlmError(f"model returned no structured output for {schema.__name__}")
        if self._trace:
            log.debug("structured %s -> %s", schema.__name__, out)
        return out

    def text(self, prompt: Prompt, tier: ModelTier = ModelTier.FAST, context: LlmContext | None = None) -> str:
        try:
            content = self._models[tier].invoke(self._messages(prompt)).content
        except Exception as e:
            raise self._classify(e, "text call failed") from e
        text = content if isinstance(content, str) else "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
        if not text.strip():
            raise LlmError("model returned an empty response")
        return text

    @staticmethod
    def _classify(error: Exception, what: str) -> LlmError:
        """Output that could not be parsed is a plain LlmError (a repair or fallback may help); anything else is a service problem."""
        from langchain_core.exceptions import OutputParserException

        if isinstance(error, (OutputParserException, ValueError)):
            return LlmError(f"{what}: {error}")
        return LlmUnavailableError(f"{what}: {error}")

    @staticmethod
    def _messages(prompt: Prompt) -> list[tuple[str, str]]:
        return [("system", prompt.system), ("human", prompt.user)]
