"""Two-layer semantic cache on a pluggable CacheStore (in-memory TTL/LRU, or Postgres when DATABASE_URL is set).
 plan layer  : normalised question (+ conversation context) -> {sql, ir, ...}  (skips the LLM generation call)
 result layer: canonical intent                             -> result          (skips the engine; equivalent SQL shares an entry)
Cache failures never fail a turn."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import asdict, dataclass

from app.core.config import Settings
from app.core.enums import CacheLayer, QueryMode, StoreKind
from app.core.logging import get_logger
from app.cache.store import CacheStore, MemoryCacheStore
from app.query.ir import QueryIR
from app.query.normalizer import Intent
from app.query.period import Period

log = get_logger("cache")


@dataclass
class CacheStats:
    plan_hits: int = 0
    plan_misses: int = 0
    result_hits: int = 0
    result_misses: int = 0
    plan_entries: int = 0
    result_entries: int = 0


def create_cache_store(settings: Settings) -> CacheStore:
    if settings.cache_store == StoreKind.POSTGRES:
        from app.cache.postgres_store import PostgresCacheStore  # imported lazily: psycopg pool only when configured
        return PostgresCacheStore(settings.database_url, settings.cache_ttl_s)
    return MemoryCacheStore(settings.cache_ttl_s, settings.cache_max_entries)


class SemanticCache:
    def __init__(self, settings: Settings, store: CacheStore | None = None) -> None:
        self.enabled = settings.cache_enabled
        self._store = store or create_cache_store(settings)
        self._stats = CacheStats()
        self._lock = threading.Lock()

    # ---- keys ----
    @staticmethod
    def plan_key(question: str, context: str = "") -> str:
        """context: anything that changes the meaning of the question (the previous SQL for follow-ups)."""
        normalised = re.sub(r"[^a-z0-9 ]", "", question.lower()).strip()
        return _digest(f"{normalised}|{context}")

    @staticmethod
    def result_key(ir: QueryIR, period: Period, mode: QueryMode) -> str:
        # Order of metrics and dimensions is part of the key: it is the column order of the result.
        canon = {"m": ir.metrics, "d": ir.dimensions,
                 "f": sorted((f.dim, sorted(f.values), f.negate) for f in ir.filters),
                 "s": str(period.start), "e": str(period.end), "g": ir.grain.value, "o": ir.order_by,
                 "od": ir.order_desc, "l": ir.limit, "mode": mode.value}
        return _digest(json.dumps(canon, default=str))

    @classmethod
    def intent_key(cls, intent: Intent, mode: QueryMode) -> str:
        """Equivalent SQL shares an entry when the intent is exact; anything else is keyed on the normalised SQL text."""
        if intent.exact and intent.ir and intent.period:
            return cls.result_key(intent.ir, intent.period, mode)
        return _digest(f"sql|{intent.fingerprint}|{mode.value}")

    # ---- plan layer ----
    def get_plan(self, key: str) -> dict | None:
        return self._get(CacheLayer.PLAN, key)

    def put_plan(self, key: str, plan: dict) -> None:
        self._put(CacheLayer.PLAN, key, plan)

    # ---- result layer ----
    def get_result(self, key: str) -> dict | None:
        return self._get(CacheLayer.RESULT, key)

    def put_result(self, key: str, result: dict) -> None:
        self._put(CacheLayer.RESULT, key, result)

    # ---- admin ----
    def stats(self) -> dict:
        with self._lock:
            snapshot = CacheStats(**{**asdict(self._stats), "plan_entries": self._store.size(CacheLayer.PLAN),
                                     "result_entries": self._store.size(CacheLayer.RESULT)})
        return asdict(snapshot)

    def clear(self) -> None:
        self._store.clear()
        with self._lock:
            self._stats = CacheStats()

    def close(self) -> None:
        self._store.close()

    # ---- internals ----
    def _get(self, layer: CacheLayer, key: str) -> dict | None:
        hit = None
        if self.enabled:
            try:
                hit = self._store.get(layer, key)
            except Exception as e:  # a broken store must not fail the turn
                log.warning("cache get failed: %s", e)
        self._count(layer, hit is not None)
        return hit

    def _put(self, layer: CacheLayer, key: str, value: dict) -> None:
        if not self.enabled:
            return
        try:
            self._store.put(layer, key, value)
        except Exception as e:
            log.warning("cache put failed: %s", e)

    def _count(self, layer: CacheLayer, hit: bool) -> None:
        with self._lock:
            name = f"{layer.value}_{'hits' if hit else 'misses'}"
            setattr(self._stats, name, getattr(self._stats, name) + 1)


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()
