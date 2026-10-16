from __future__ import annotations

from app.query.period import Period
from app.rca.models import DrillReport, SegmentContribution
from app.rca.reader import Cell, Segment, SegmentReader, relative_change
from app.semantic.catalog import Catalog
from app.semantic.models import MetricSpec


def contributions(now: dict[Segment, Cell], before: dict[Segment, Cell], ratio: bool) -> dict[Segment, float]:
    """Per-segment contribution to the change of the total; contributions sum exactly to the delta.
    Additive metric: value change. Ratio metric: mix effect + rate effect (Kitagawa), so a volume change in a segment
    whose ratio equals the average contributes ~0 instead of being mis-attributed."""
    keys = set(now) | set(before)
    if not ratio:
        return {k: now.get(k, Cell(0, None)).num - before.get(k, Cell(0, None)).num for k in keys}
    d1, d0 = sum(c.den for c in now.values()), sum(c.den for c in before.values())
    r0_total = sum(c.num for c in before.values()) / d0 if d0 else 0.0
    out = {}
    for k in keys:
        c1, c0 = now.get(k, Cell(0, 0)), before.get(k, Cell(0, 0))
        w1, w0 = (c1.den / d1 if d1 else 0.0), (c0.den / d0 if d0 else 0.0)
        r0 = c0.value if c0.den else r0_total
        r1 = c1.value if c1.den else r0
        out[k] = (w1 - w0) * (r0 - r0_total) + w1 * (r1 - r0)
    return out


class SegmentDriller:
    def __init__(self, catalog: Catalog, reader: SegmentReader) -> None:
        self._cat, self._reader = catalog, reader

    def drill(self, metric: MetricSpec, dims: list[str], marginal_dims: list[str], current: Period, baseline: Period,
              top_k: int, min_share: float) -> DrillReport:
        dims = [d for d in dims if d in metric.dimensions]
        all_dims = list(dict.fromkeys([*dims, *(d for d in marginal_dims if d in metric.dimensions)]))
        self._reader.prefetch((metric, ds, p) for ds in [dims, *([d] for d in all_dims)] for p in (current, baseline))
        now, before = self._reader.segments(metric, dims, current), self._reader.segments(metric, dims, baseline)
        contrib = contributions(now, before, metric.is_ratio)
        total = sum(contrib.values())
        base_total = sum((c.den if metric.is_ratio else c.num) or 0 for c in before.values())
        cells = []
        for key, c in contrib.items():
            c1, c0 = now.get(key, Cell(0, None if not metric.is_ratio else 0)), before.get(key, Cell(0, None if not metric.is_ratio else 0))
            base_share = ((c0.den if metric.is_ratio else c0.num) or 0) / base_total if base_total else 0
            if base_share < min_share and abs(c) < abs(total) * 0.1:
                continue  # tiny segment that does not move the total
            cells.append(self._cell(dict(zip(dims, key)), c1, c0, c, total))
        cells.sort(key=lambda r: -abs(r.contribution))
        marginals = {}
        for dim in dict.fromkeys([*dims, *(d for d in marginal_dims if d in metric.dimensions)]):
            m_now, m_before = self._reader.segments(metric, [dim], current), self._reader.segments(metric, [dim], baseline)
            m_contrib = contributions(m_now, m_before, metric.is_ratio)
            if m_contrib:
                key = max(m_contrib, key=lambda k: abs(m_contrib[k]))
                marginals[dim] = self._cell({dim: key[0]}, m_now.get(key, Cell(0, 0 if metric.is_ratio else None)),
                                            m_before.get(key, Cell(0, 0 if metric.is_ratio else None)), m_contrib[key], total)
        return DrillReport(dims=dims, total_change=total, cells=cells[:top_k], marginals=marginals)

    @staticmethod
    def _cell(segment: dict[str, str], c1: Cell, c0: Cell, contribution: float, total: float) -> SegmentContribution:
        v1, v0 = c1.value, c0.value
        return SegmentContribution(segment=segment, baseline=v0, current=v1, rel=relative_change(v1, v0), contribution=contribution,
                                   share_of_change=contribution / total if total else None)
