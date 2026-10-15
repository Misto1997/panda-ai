from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import EngineKind, LlmProvider

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # LLM
    llm_provider: LlmProvider = LlmProvider.MOCK
    gemini_model: str = "gemini-2.5-flash"
    gemini_pro_model: str = "gemini-2.5-pro"
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    llm_timeout_s: float = 45.0
    llm_max_retries: int = 2

    # Engine
    engine: EngineKind = EngineKind.DUCKDB
    duckdb_path: str = str(ROOT / "backend" / "data" / "panda.duckdb")
    max_rows: int = 500
    query_timeout_s: float = 20.0

    # Optional Postgres (pgvector search + LangGraph checkpointer). Empty = in-memory fallbacks.
    database_url: str = ""

    # Semantic layer and cache
    semantic_dir: str = str(ROOT / "semantic")
    cache_enabled: bool = True
    cache_ttl_s: int = 600
    cache_max_entries: int = 512

    # API
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    max_question_chars: int = 1000
    sse_heartbeat_s: float = 15.0

    # Observability. TRACE_PAYLOADS adds prompts, SQL and raw LLM output to DEBUG logs and step events.
    log_level: str = "INFO"
    trace_payloads: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
