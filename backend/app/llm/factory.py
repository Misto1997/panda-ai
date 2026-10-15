from app.core.config import Settings
from app.core.enums import LlmProvider
from app.llm.base import LlmClient


def create_llm(settings: Settings) -> LlmClient:
    if settings.llm_provider == LlmProvider.GEMINI:
        from app.llm.gemini import GeminiLlm
        return GeminiLlm(settings)
    from app.llm.mock import MockLlm
    return MockLlm()
