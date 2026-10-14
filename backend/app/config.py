from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # LLM: mock needs no credentials; gemini uses AI Studio key (GOOGLE_API_KEY) or Vertex (GOOGLE_GENAI_USE_VERTEXAI)
    llm_provider: str = "mock"  # mock | gemini
    gemini_model: str = "gemini-2.5-flash"
    gemini_pro_model: str = "gemini-2.5-pro"
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768

    # Engine: duckdb locally, bigquery in phase 2
    engine: str = "duckdb"
    duckdb_path: str = str(ROOT / "backend" / "data" / "panda.duckdb")
    max_rows: int = 500

    # Optional Postgres (checkpointer + pgvector). Empty = in-memory fallbacks.
    database_url: str = ""

    semantic_dir: str = str(ROOT / "semantic")
    cache_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
