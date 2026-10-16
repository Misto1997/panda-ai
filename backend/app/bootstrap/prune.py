"""Housekeeping for conversation state: delete LangGraph checkpoints of threads idle for more than N days, and expired cache rows.
Run nightly (after the data refresh) or by hand:  python -m app.bootstrap prune --days 7"""
from __future__ import annotations

from app.core.config import Settings
from app.core.db import PgPool
from app.core.enums import StoreKind
from app.core.logging import get_logger

log = get_logger("bootstrap.prune")
CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")  # children first
STALE_THREADS_SQL = ("SELECT thread_id FROM checkpoints GROUP BY thread_id "
                     "HAVING max((checkpoint->>'ts')::timestamptz) < now() - make_interval(days => %s)")


def prune(settings: Settings, days: int = 7, pool: PgPool | None = None) -> dict[str, int]:
    """Returns what was removed. A no-op when nothing is stored in Postgres."""
    if settings.checkpointer != StoreKind.POSTGRES and settings.cache_store != StoreKind.POSTGRES:
        return {}
    owned = pool is None
    pool = pool or PgPool.from_settings(settings)
    removed: dict[str, int] = {}
    try:
        with pool.connection() as conn:
            if settings.checkpointer == StoreKind.POSTGRES:
                threads = [r[0] for r in conn.execute(STALE_THREADS_SQL, (days,)).fetchall()]
                if threads:
                    with conn.transaction():
                        for table in CHECKPOINT_TABLES:
                            removed[table] = conn.execute(f"DELETE FROM {table} WHERE thread_id = ANY(%s)", (threads,)).rowcount
                removed["threads"] = len(threads)
            if settings.cache_store == StoreKind.POSTGRES:
                removed["cache_rows"] = conn.execute("DELETE FROM panda_cache WHERE created_at < now() - make_interval(secs => %s)",
                                                     (settings.cache_ttl_s,)).rowcount
    finally:
        if owned:
            pool.close()
    log.info("pruned %s", removed)
    return removed
