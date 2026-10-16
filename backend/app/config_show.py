"""Print the effective configuration (secrets redacted).   python -m app.config_show   |   PANDA_PROFILE=prod python -m app.config_show"""
from __future__ import annotations

from app.core.config import ROOT, get_settings, profile_path

SHOW = ["app_env", "llm_provider", "google_genai_use_vertexai", "google_cloud_project", "google_cloud_location", "gemini_model",
        "engine", "duckdb_path", "bq_dataset", "bq_location", "search_backend", "checkpointer", "cache_store", "quota_store",
        "auth_mode", "text_to_sql", "cache_enabled", "daily_user_query_limit", "daily_global_query_limit", "log_level", "trace_payloads"]


def main() -> None:
    s = get_settings()
    print(f"profile      : {s.profile}  ({profile_path().relative_to(ROOT) if profile_path().exists() else 'no file, defaults'})")
    for key in SHOW:
        print(f"{key:26s}: {getattr(s, key)}")
    print(f"{'database_url':26s}: {'set (' + s.database_url.split('@')[-1] + ')' if s.database_url else 'empty'}")
    print("OK: configuration is consistent")


if __name__ == "__main__":
    main()
