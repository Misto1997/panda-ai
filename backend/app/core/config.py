import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, YamlConfigSettingsSource

from app.core.enums import (AppEnv, AuthMode, EmbeddingProvider, EngineKind, LlmProvider, SearchBackendKind, StoreKind, VectorIndexKind)
from app.core.errors import ConfigurationError

ROOT = Path(__file__).resolve().parents[3]
PROFILE_DIR = ROOT / "config" / "profiles"


def active_profile() -> str:
    """PANDA_PROFILE from the environment, then .env, default 'local'."""
    return (os.environ.get("PANDA_PROFILE") or dotenv_values(ROOT / ".env").get("PANDA_PROFILE") or "local").strip()


def profile_path() -> Path:
    return Path(os.environ.get("PANDA_PROFILE_FILE") or PROFILE_DIR / f"{active_profile()}.yaml")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # Profile: precedence is init args > environment > .env > config/profiles/<PANDA_PROFILE>.yaml > defaults below.
    app_env: AppEnv = AppEnv.LOCAL
    profile: str = Field(default_factory=active_profile)

    # Where state lives. Explicit so local and prod can differ per component; POSTGRES kinds need DATABASE_URL.
    search_backend: SearchBackendKind = SearchBackendKind.MEMORY
    checkpointer: StoreKind = StoreKind.MEMORY
    cache_store: StoreKind = StoreKind.MEMORY
    quota_store: StoreKind = StoreKind.MEMORY

    # LLM
    llm_provider: LlmProvider = LlmProvider.MOCK
    gemini_model: str = "gemini-3.8-flash"      # ModelTier.FAST (unverified id: confirm in the Vertex model garden)
    gemini_thinking_level: str = "low"        # Gemini 3 thinking: low | medium | high (minimal/none are not accepted by 3.8 Flash); medium is the slow default
    gemini_pro_model: str = "gemini-3.8-flash"  # ModelTier.REASONING; point at a Pro model if budget allows
    embedding_provider: EmbeddingProvider = EmbeddingProvider.AUTO  # hash = no embedding quota needed (rebuild the index after changing)
    embedding_model: str = "gemini-embedding-2"
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

    # Postgres (AlloyDB or Cloud SQL). Used only by components whose kind above is POSTGRES / PGVECTOR.
    database_url: str = ""                      # put the password in PGPASSWORD, not in the URL
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
    admin_emails: str = ""                    # comma-separated Google accounts allowed to call /api/admin/* in firebase mode
    daily_user_query_limit: int = 30
    daily_global_query_limit: int = 300
    max_request_bytes: int = 16 * 1024
    ip_rate_per_minute: int = 120               # per-IP token bucket refill; burst = ip_rate_burst
    ip_rate_burst: int = 20

    # Observability. TRACE_PAYLOADS adds prompts, SQL and raw LLM output to DEBUG logs and step events.
    log_level: str = "INFO"
    trace_payloads: bool = False


    @classmethod
    def settings_customise_sources(cls, settings_cls: type[BaseSettings], init_settings: PydanticBaseSettingsSource,
                                   env_settings: PydanticBaseSettingsSource, dotenv_settings: PydanticBaseSettingsSource,
                                   file_secret_settings: PydanticBaseSettingsSource) -> tuple[PydanticBaseSettingsSource, ...]:
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings, dotenv_settings]
        path = profile_path()
        if path.exists():
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=path))
        elif active_profile() != "local":
            raise ConfigurationError(f"profile '{active_profile()}' not found: expected {path}")
        return tuple(sources)

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def uses_postgres(self) -> bool:
        return StoreKind.POSTGRES in (self.checkpointer, self.cache_store, self.quota_store) or self.search_backend == SearchBackendKind.PGVECTOR

    @model_validator(mode="after")
    def _consistent(self) -> "Settings":
        errs: list[str] = []
        if self.uses_postgres and not self.database_url:
            errs.append("a component is set to postgres/pgvector but DATABASE_URL is empty")
        if self.engine == EngineKind.BIGQUERY and not self.google_cloud_project:
            errs.append("engine=bigquery needs google_cloud_project")
        if self.llm_provider == LlmProvider.GEMINI and self.google_genai_use_vertexai and not self.google_cloud_project:
            errs.append("llm_provider=gemini with Vertex needs google_cloud_project")
        if self.auth_mode == AuthMode.FIREBASE and not self.firebase_project_id:
            errs.append("auth_mode=firebase needs firebase_project_id")
        if self.app_env == AppEnv.PROD:  # the production suite, enforced
            wanted = {"llm_provider": (self.llm_provider, LlmProvider.GEMINI), "google_genai_use_vertexai": (self.google_genai_use_vertexai, True),
                      "engine": (self.engine, EngineKind.BIGQUERY), "search_backend": (self.search_backend, SearchBackendKind.PGVECTOR),
                      "checkpointer": (self.checkpointer, StoreKind.POSTGRES), "cache_store": (self.cache_store, StoreKind.POSTGRES),
                      "quota_store": (self.quota_store, StoreKind.POSTGRES), "auth_mode": (self.auth_mode, AuthMode.FIREBASE),
                      "trace_payloads": (self.trace_payloads, False), "cache_enabled": (self.cache_enabled, True)}
            errs += [f"app_env=prod requires {k}={want}, got {got}" for k, (got, want) in wanted.items() if got != want]
        if errs:
            raise ValueError("; ".join(errs))
        return self


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as e:
        problems = "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())
        raise ConfigurationError(f"invalid configuration (profile '{active_profile()}', file {profile_path()}): {problems}") from e
