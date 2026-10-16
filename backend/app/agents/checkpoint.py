from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import Settings
from app.core.enums import StoreKind
from app.core.logging import get_logger

log = get_logger("agent.checkpoint")


def create_checkpointer(settings: Settings) -> tuple[BaseCheckpointSaver, callable]:
    """Returns (saver, close). Postgres when settings.checkpointer is POSTGRES (stateless, multi-instance safe), else in-memory."""
    if settings.checkpointer != StoreKind.POSTGRES:
        log.info("checkpointer: in-memory (conversations are lost on restart)")
        return MemorySaver(), lambda: None
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(settings.database_url, max_size=10, kwargs={"autocommit": True, "prepare_threshold": 0}, open=True)
    saver = PostgresSaver(pool)
    saver.setup()
    log.info("checkpointer: postgres")
    return saver, pool.close
