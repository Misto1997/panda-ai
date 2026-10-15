"""Two-layer semantic cache (in-process; the store is swappable for Postgres/Redis in phase 2).
 plan layer  : normalised question (+ conversation context) -> QueryIR   (skips the LLM planning call)
 result layer: canonical resolved intent                    -> result    (skips the engine; paraphrases share an entry)"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Generic, TypeVar

from app.core.config import Settings
from app.core.enums import QueryMode
from app.query.ir import QueryIR
from app.query.period import Period

T = TypeVar("T")


class TtlLruCache(Generic[T]):
    def __init__(self, ttl_s: float, max_entries: int) -> None:
        self._ttl, self._max = ttl_s, max_entries
        self._data: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> T | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if time.monotonic() - entry[0] > self._ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return entry[1]

    def put(self, key: str, value: T) -> None:
        with self._lock:
            self._data[key] = (time.monotonic(), value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


@dataclass
class CacheStats:
    plan_hits: int = 0
    plan_misses: int = 0
    result_hits: int = 0
    result_misses: int = 0
    plan_entries: int = 0
    result_entries: int = 0


class SemanticCache:
    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.cache_enabled
        self._plans: TtlLruCache[dict] = TtlLruCache(settings.cache_ttl_s, settings.cache_max_entries)
        self._results: TtlLruCache[dict] = TtlLruCache(settings.cache_ttl_s, settings.cache_max_entries)
        self._stats = CacheStats()
        self._lock = threading.Lock()

    # ---- keys ----
    @staticmethod
    def plan_key(question: str, prior_metrics: list[str]) -> str:
        normalised = re.sub(r"[^a-z0-9 ]", "", question.lower()).strip()
        return f"{normalised}|{','.join(sorted(prior_metrics))}"

    @staticmethod
    def result_key(ir: QueryIR, period: Period, mode: QueryMode) -> str:
        canon = {"m": sorted(ir.metrics), "d": sorted(ir.dimensions),
                 "f": sorted((f.dim, sorted(f.values), f.negate) for f in ir.filters),
                 "s": str(period.start), "e": str(period.end), "g": ir.grain.value, "o": ir.order_by,
                 "od": ir.order_desc, "l": ir.limit, "mode": mode.value}
        return hashlib.sha1(json.dumps(canon, default=str).encode()).hexdigest()

    # ---- plan layer ----
    def get_plan(self, key: str) -> dict | None:
        hit = self._plans.get(key) if self.enabled else None
        self._count("plan", hit is not None)
        return hit

    def put_plan(self, key: str, plan: dict) -> None:
        if self.enabled:
            self._plans.put(key, plan)

    # ---- result layer ----
    def get_result(self, key: str) -> dict | None:
        hit = self._results.get(key) if self.enabled else None
        self._count("result", hit is not None)
        return hit

    def put_result(self, key: str, result: dict) -> None:
        if self.enabled:
            self._results.put(key, result)

    # ---- admin ----
    def stats(self) -> dict:
        with self._lock:
            return asdict(CacheStats(**{**asdict(self._stats), "plan_entries": len(self._plans), "result_entries": len(self._results)}))

    def clear(self) -> None:
        self._plans.clear()
        self._results.clear()
        with self._lock:
            self._stats = CacheStats()

    def _count(self, layer: str, hit: bool) -> None:
        with self._lock:
            name = f"{layer}_{'hits' if hit else 'misses'}"
            setattr(self._stats, name, getattr(self._stats, name) + 1)
