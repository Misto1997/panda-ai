from pathlib import Path

import pytest

from app.container import build_container
from app.core.config import Settings, get_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    s = get_settings()
    if not Path(s.duckdb_path).exists():
        pytest.skip("synthetic data missing: run `make data` first")
    return s.model_copy(update={"llm_provider": "mock", "database_url": "", "cache_enabled": True})


@pytest.fixture(scope="session")
def container(settings):
    c = build_container(settings)
    yield c
    c.close()
