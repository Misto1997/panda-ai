from app.core.config import Settings
from app.core.enums import LlmProvider
from app.llm.base import LlmClient
from app.llm.budget import BudgetedLlm


def create_llm(settings: Settings) -> LlmClient:
    if settings.llm_provider == LlmProvider.GEMINI:
        from app.llm.gemini import GeminiLlm
        return BudgetedLlm(GeminiLlm(settings), settings.llm_max_concurrency)
    from app.llm.mock import MockLlm
    return BudgetedLlm(MockLlm())
