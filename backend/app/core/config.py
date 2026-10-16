from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import AuthMode, EngineKind, LlmProvider, VectorIndexKind

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # LLM
    llm_provider: LlmProvider = LlmProvider.MOCK
    gemini_model: str = "gemini-3.8-flash"      # ModelTier.FAST (unverified id: confirm in the Vertex model garden)
    gemini_pro_model: str = "gemini-3.8-flash"  # ModelTier.REASONING; point at a Pro model if budget allows
    embedding_model: str = "gemini-embedding-001"
    llm_max_calls_per_turn: int = 8             # hard cap on model calls inside one chat turn (runaway-loop guard)
    # Vertex AI / Gemini Enterprise Agent Platform: keyless via Application Default Credentials (Cloud Run service account).
    google_genai_use_vertexai: bool = False
    google_cloud_project: str = ""
    google_cloud_location: str = "global"
    embedding_location: str = ""                # empty = google_cloud_location; embedding models may need a regional endpoint
    embedding_dim: int = 768
    llm_timeout_s: float = 45.0
    llm_max_retries: int = 2

    # Engine
    engine: EngineKind = EngineKind.DUCKDB
    duckdb_path: str = str(ROOT / "backend" / "data" / "panda.duckdb")
    bq_dataset: str = "panda"
    bq_location: str = "asia-southeast1"
    bq_max_bytes_billed: int = 10 * 1024**3     # per query; BigQuery rejects queries that would bill more
    max_rows: int = 500
    query_timeout_s: float = 20.0

    # Text-to-SQL (guarded generation; QueryIR compiler is the deterministic fallback)
    text_to_sql: bool = True
    sql_max_repairs: int = 2
    sql_max_joins: int = 3
    sql_max_chars: int = 6000
    sql_max_bytes_processed: int = 0   # reject a query whose dry-run scan exceeds this (0 = off; BigQuery reports bytes)

    # Optional Postgres (pgvector search + LangGraph checkpointer). Empty = in-memory fallbacks.
    database_url: str = ""                      # AlloyDB or Cloud SQL; put the password in PGPASSWORD, not in the URL
    db_pool_max: int = 5
    db_connect_timeout_s: float = 5.0
    db_pool_timeout_s: float = 10.0
    vector_index: VectorIndexKind = VectorIndexKind.NONE

    # Semantic layer and cache
    semantic_dir: str = str(ROOT / "semantic")
    cache_enabled: bool = True
    cache_ttl_s: int = 600
    cache_max_entries: int = 512   # per layer, in-memory store only (Postgres store relies on the TTL)

    # API
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    max_question_chars: int = 1000
    sse_heartbeat_s: float = 15.0

    # Auth and abuse controls
    auth_mode: AuthMode = AuthMode.DEV
    firebase_project_id: str = ""
    daily_user_query_limit: int = 30
    daily_global_query_limit: int = 300
    max_request_bytes: int = 16 * 1024
    ip_rate_per_minute: int = 120               # per-IP token bucket refill; burst = ip_rate_burst
    ip_rate_burst: int = 20

    # Observability. TRACE_PAYLOADS adds prompts, SQL and raw LLM output to DEBUG logs and step events.
    log_level: str = "INFO"
    trace_payloads: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
