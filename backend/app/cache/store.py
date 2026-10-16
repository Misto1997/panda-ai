"""Storage port of the semantic cache plus the in-process TTL/LRU implementation."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Protocol, runtime_checkable

from app.core.enums import CacheLayer


@runtime_checkable
class CacheStore(Protocol):
    """Key/value store with a TTL. Values are JSON-serialisable dicts. Implementations must never raise for a missing or
    expired key; backend outages should degrade to a miss (the cache is an optimisation, never a dependency)."""
    name: str

    def get(self, layer: CacheLayer, key: str) -> dict | None: ...
    def put(self, layer: CacheLayer, key: str, value: dict) -> None: ...
    def size(self, layer: CacheLayer) -> int: ...
    def clear(self) -> None: ...
    def close(self) -> None: ...


class _TtlLru:
    def __init__(self, ttl_s: float, max_entries: int) -> None:
        self._ttl, self._max = ttl_s, max_entries
        self._data: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> dict | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if time.monotonic() - entry[0] > self._ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return entry[1]

    def put(self, key: str, value: dict) -> None:
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


class MemoryCacheStore:
    name = "memory"

    def __init__(self, ttl_s: float, max_entries: int) -> None:
        self._layers = {layer: _TtlLru(ttl_s, max_entries) for layer in CacheLayer}

    def get(self, layer: CacheLayer, key: str) -> dict | None:
        return self._layers[layer].get(key)

    def put(self, layer: CacheLayer, key: str, value: dict) -> None:
        self._layers[layer].put(key, value)

    def size(self, layer: CacheLayer) -> int:
        return len(self._layers[layer])

    def clear(self) -> None:
        for lru in self._layers.values():
            lru.clear()

    def close(self) -> None:
        pass
