import pytest

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError


@pytest.fixture
def fresh(monkeypatch):
    """Isolated settings: no ambient env, cache cleared before and after."""
    for key in ("PANDA_PROFILE", "PANDA_PROFILE_FILE", "DATABASE_URL", "LLM_PROVIDER", "ENGINE", "SEARCH_BACKEND", "AUTH_MODE"):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_local_profile_runs_with_zero_infrastructure(fresh):
    s = get_settings()
    assert (s.profile, s.app_env.value, s.llm_provider.value, s.engine.value) == ("local", "local", "mock", "duckdb")
    assert not s.uses_postgres


def test_env_overrides_the_yaml_profile(fresh):
    fresh.setenv("ENGINE", "bigquery")
    fresh.setenv("GOOGLE_CLOUD_PROJECT", "p")
    assert get_settings().engine.value == "bigquery"


def test_prod_profile_is_the_full_production_suite(fresh):
    fresh.setenv("PANDA_PROFILE", "prod")
    fresh.setenv("DATABASE_URL", "postgresql://u@10.0.0.1/panda")
    s = get_settings()
    assert (s.llm_provider.value, s.engine.value, s.search_backend.value, s.checkpointer.value, s.auth_mode.value) == \
        ("gemini", "bigquery", "pgvector", "postgres", "firebase")


@pytest.mark.parametrize("override, fragment", [
    ({"LLM_PROVIDER": "mock"}, "requires llm_provider"),
    ({"ENGINE": "duckdb"}, "requires engine"),
    ({"AUTH_MODE": "dev"}, "requires auth_mode"),
    ({"TRACE_PAYLOADS": "true"}, "requires trace_payloads"),
])
def test_prod_refuses_a_downgraded_component(fresh, override, fragment):
    fresh.setenv("PANDA_PROFILE", "prod")
    fresh.setenv("DATABASE_URL", "postgresql://u@10.0.0.1/panda")
    for k, v in override.items():
        fresh.setenv(k, v)
    with pytest.raises(ConfigurationError, match=fragment):
        get_settings()


def test_postgres_components_need_a_database_url(fresh):
    fresh.setenv("SEARCH_BACKEND", "pgvector")
    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        get_settings()


def test_unknown_profile_fails_loudly(fresh):
    fresh.setenv("PANDA_PROFILE", "nope")
    with pytest.raises(ConfigurationError, match="not found"):
        get_settings()


def test_embedding_provider_can_be_forced_offline_without_touching_the_llm(fresh):
    from app.llm.embeddings import HashEmbedder, create_embedder
    fresh.setenv("EMBEDDING_PROVIDER", "hash")
    fresh.setenv("LLM_PROVIDER", "mock")
    s = get_settings()
    assert isinstance(create_embedder(s), HashEmbedder)
