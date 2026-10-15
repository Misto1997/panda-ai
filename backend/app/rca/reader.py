from __future__ import annotations

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

    def __init__(self, service: QueryService) -> None:
        self._service = service
        self.queries: list[str] = []

    def segments(self, metric: MetricSpec, dims: Sequence[str], period: Period, filters: Sequence[Filter] = ()) -> dict[Segment, Cell]:
        ir = QueryIR(metrics=[metric.id], dimensions=list(dims), filters=[f.model_copy() for f in filters], time_expr=period.as_expr())
        outcome = self._service.execute(ir, use_cache=False, split_ratios=True)
        self.queries.append(outcome.compiled.sql)
        index = {name: i for i, name in enumerate(outcome.result.columns)}
        out: dict[Segment, Cell] = {}
        for row in outcome.result.rows:
            key = tuple(str(row[index[d]]) for d in dims)
            if metric.is_ratio:
                out[key] = Cell(row[index[f"{metric.id}__num"]] or 0.0, row[index[f"{metric.id}__den"]] or 0.0)
            else:
                out[key] = Cell(row[index[metric.id]] or 0.0, None)
        return out

    def value(self, metric: MetricSpec, period: Period, filters: Sequence[Filter] = ()) -> float | None:
        cell = self.segments(metric, [], period, filters).get(())
        return cell.value if cell else None
