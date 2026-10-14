"""Two-layer semantic cache (in-process; phase 2 moves it to Postgres).
 L1: normalised question -> QueryIR   (skips the LLM planning call)
 L2: canonical resolved IR  -> result (skips the engine; paraphrases share one entry)"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import OrderedDict

from app.config import get_settings

TTL_S = 600
MAX = 512


def norm_question(q: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", q.lower()).strip()


def ir_key(ir: dict, start: str, end: str, mode: str) -> str:
    canon = {"m": sorted(ir["metrics"]), "d": sorted(ir["dimensions"]),
             "f": sorted((f["dim"], tuple(sorted(f["values"])), f["negate"]) for f in ir["filters"]),
             "s": start, "e": end, "g": ir["grain"], "o": ir["order_by"], "od": ir["order_desc"], "l": ir["limit"], "mode": mode}
    return hashlib.sha1(json.dumps(canon, default=str).encode()).hexdigest()


class _LRU:
    def __init__(self) -> None:
        self.d: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def get(self, k: str):
        v = self.d.get(k)
        if not v or time.time() - v[0] > TTL_S:
            self.d.pop(k, None)
            return None
        self.d.move_to_end(k)
        return v[1]

    def put(self, k: str, val) -> None:
        self.d[k] = (time.time(), val)
        while len(self.d) > MAX:
            self.d.popitem(last=False)


plans, results = _LRU(), _LRU()
stats = {"plan_hits": 0, "plan_misses": 0, "result_hits": 0, "result_misses": 0}


def enabled() -> bool:
    return get_settings().cache_enabled


def clear() -> None:
    plans.d.clear(); results.d.clear()
    for k in stats:
        stats[k] = 0
