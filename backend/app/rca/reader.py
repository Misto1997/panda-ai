from __future__ import annotations

import threading
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple, Sequence

from app.query.ir import Filter, QueryIR
from app.query.period import Period
from app.query.service import QueryService
from app.semantic.models import MetricSpec

Segment = tuple[str, ...]


class Cell(NamedTuple):
    """Numerator/denominator for ratio metrics; (value, None) for additive metrics."""
    num: float
    den: float | None

    @property
    def value(self) -> float | None:
        if self.den is None:
            return self.num
        return self.num / self.den if self.den else None


def relative_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old)


class SegmentReader:
    """Reads governed metric values per segment through the QueryService. Records every SQL statement it runs."""

    def __init__(self, service: QueryService, pool: ThreadPoolExecutor | None = None) -> None:
        self._service, self._pool = service, pool
        self.queries: list[str] = []
        self._memo: dict[tuple, dict[Segment, Cell]] = {}
        self._lock = threading.Lock()

    def prefetch(self, requests: Iterable[tuple[MetricSpec, Sequence[str], Period]]) -> None:
        """Run independent warehouse reads concurrently (each is a 1-2 s round trip on BigQuery); results are memoised for the callers."""
        reqs = list(requests)
        if self._pool is None or len(reqs) < 2:
            return
        for future in [self._pool.submit(self.segments, m, d, p) for m, d, p in reqs]:
            future.result()  # surface the first failure here instead of silently later

    def segments(self, metric: MetricSpec, dims: Sequence[str], period: Period, filters: Sequence[Filter] = ()) -> dict[Segment, Cell]:
        memo_key = (metric.id, tuple(dims), period.start, period.end, tuple((f.dim, tuple(f.values), f.negate) for f in filters))
        with self._lock:
            if memo_key in self._memo:
                return self._memo[memo_key]
        ir = QueryIR(metrics=[metric.id], dimensions=list(dims), filters=[f.model_copy() for f in filters], time_expr=period.as_expr())
        outcome = self._service.execute(ir, use_cache=False, split_ratios=True)
        with self._lock:
            self.queries.append(outcome.compiled.sql)
        index = {name: i for i, name in enumerate(outcome.result.columns)}
        out: dict[Segment, Cell] = {}
        for row in outcome.result.rows:
            seg = tuple(str(row[index[d]]) for d in dims)
            if metric.is_ratio:
                num, den = row[index[f"{metric.id}__num"]], row[index[f"{metric.id}__den"]]
                if num is None and den is None:
                    continue  # no data in this period: 'missing' must not look like 'zero'
                out[seg] = Cell(num or 0.0, den or 0.0)
            elif row[index[metric.id]] is not None:
                out[seg] = Cell(row[index[metric.id]], None)
        with self._lock:
            self._memo[memo_key] = out
        return out

    def value(self, metric: MetricSpec, period: Period, filters: Sequence[Filter] = ()) -> float | None:
        cell = self.segments(metric, [], period, filters).get(())
        return cell.value if cell else None
