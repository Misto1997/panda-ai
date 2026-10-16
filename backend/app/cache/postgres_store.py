"""Postgres-backed CacheStore (selected when DATABASE_URL is set). Shared by every instance, survives restarts.
Not exercised by the automated tests (no server in CI): kept deliberately small, parameterised and failure-tolerant."""
from __future__ import annotations

import threading

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool, PoolTimeout

from app.core.enums import CacheLayer
from app.core.logging import get_logger

log = get_logger("cache.postgres")
DDL = """
CREATE TABLE IF NOT EXISTS panda_cache (
  key text NOT NULL, layer text NOT NULL, value jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (layer, key));
CREATE INDEX IF NOT EXISTS panda_cache_created ON panda_cache (created_at);
"""
PURGE_EVERY = 200  # puts between sweeps of expired rows
POOL_TIMEOUT_S = 2.0


class PostgresCacheStore:
    name = "postgres"

    def __init__(self, url: str, ttl_s: float, max_pool: int = 4) -> None:
        self._ttl, self._puts, self._lock = ttl_s, 0, threading.Lock()
        self._pool = ConnectionPool(url, min_size=1, max_size=max_pool, timeout=POOL_TIMEOUT_S, open=False,
                                    kwargs={"autocommit": True, "connect_timeout": 5})
        self._ready = False

    def get(self, layer: CacheLayer, key: str) -> dict | None:
        row = self._run("SELECT value FROM panda_cache WHERE layer = %s AND key = %s AND created_at > now() - make_interval(secs => %s)",
                        (layer.value, key, self._ttl), fetch=True)
        return row[0][0] if row else None

    def put(self, layer: CacheLayer, key: str, value: dict) -> None:
        self._run("INSERT INTO panda_cache (layer, key, value) VALUES (%s, %s, %s) "
                  "ON CONFLICT (layer, key) DO UPDATE SET value = EXCLUDED.value, created_at = now()",
                  (layer.value, key, Jsonb(value)))
        with self._lock:
            self._puts += 1
            sweep = self._puts % PURGE_EVERY == 0
        if sweep:
            self._run("DELETE FROM panda_cache WHERE created_at < now() - make_interval(secs => %s)", (self._ttl,))

    def size(self, layer: CacheLayer) -> int:
        row = self._run("SELECT count(*) FROM panda_cache WHERE layer = %s AND created_at > now() - make_interval(secs => %s)",
                        (layer.value, self._ttl), fetch=True)
        return row[0][0] if row else 0

    def clear(self) -> None:
        self._run("DELETE FROM panda_cache")

    def close(self) -> None:
        self._pool.close()

    def _run(self, sql: str, params: tuple, fetch: bool = False) -> list | None:
        try:
            if not self._ready:
                self._pool.open()
                with self._pool.connection() as conn:
                    conn.execute(DDL)
                self._ready = True
            with self._pool.connection() as conn:
                cur = conn.execute(sql, params)
                return cur.fetchall() if fetch else None
        except (psycopg.Error, PoolTimeout) as e:  # cache outage = miss, never a failed turn
            log.warning("cache store unavailable: %s", e)
            return None
