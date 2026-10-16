from __future__ import annotations

import time

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import Settings
from app.core.db import POOL_RECYCLE, conn_kwargs
from app.core.enums import StoreKind
from app.core.errors import DatabaseUnavailableError, EngineError
from app.core.logging import get_logger

log = get_logger("agent.checkpoint")
SETUP_ATTEMPTS = 4
SETUP_BACKOFF_S = 3.0


def create_checkpointer(settings: Settings) -> tuple[BaseCheckpointSaver, callable]:
    """Returns (saver, close). Postgres when settings.checkpointer is POSTGRES (stateless, multi-instance safe), else in-memory."""
    if settings.checkpointer != StoreKind.POSTGRES:
        log.info("checkpointer: in-memory (conversations are lost on restart)")
        return MemorySaver(), lambda: None
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool, PoolTimeout

    # PostgresSaver requires autocommit, prepare_threshold=0 and dict_row on the connections it is given.
    pool = ConnectionPool(settings.database_url, min_size=1, max_size=5, timeout=settings.db_pool_timeout_s, open=True,
                          check=ConnectionPool.check_connection,
                          kwargs=conn_kwargs(settings.db_connect_timeout_s, prepare_threshold=0, row_factory=dict_row), **POOL_RECYCLE)
    saver = PostgresSaver(pool)
    last: Exception | None = None
    for attempt in range(1, SETUP_ATTEMPTS + 1):  # the database may be waking up or briefly unreachable: do not crash-loop the revision
        try:
            saver.setup()
            break
        except psycopg.errors.InsufficientPrivilege as e:
            pool.close()
            raise EngineError("the database user cannot create tables in schema public. As the admin user run: "
                              "GRANT ALL ON SCHEMA public TO <app user>; (see docs/GCP_SETUP.md, section 1)") from e
        except (psycopg.OperationalError, PoolTimeout, psycopg.errors.DuplicateTable, psycopg.errors.UniqueViolation) as e:
            last = e  # DuplicateTable/UniqueViolation: another instance is creating the same tables right now; retry sees them
            log.warning("checkpointer setup attempt %d/%d failed: %s", attempt, SETUP_ATTEMPTS, e)
            time.sleep(SETUP_BACKOFF_S)
    else:
        pool.close()
        raise DatabaseUnavailableError(f"cannot reach the database to set up conversation memory: {last}")
    log.info("checkpointer: postgres")
    return saver, pool.close
