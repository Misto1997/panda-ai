from __future__ import annotations

import math

from app.query.period import Period
from app.rca.models import ComponentContribution
from app.rca.reader import SegmentReader, relative_change
from app.semantic.catalog import Catalog
from app.semantic.models import RcaTreeSpec


class LogRatioDecomposer:
    """Exact multiplicative attribution (LMDI): for G = c1 * c2 * ... the contributions sum to G1 - G0."""

    def __init__(self, catalog: Catalog, reader: SegmentReader) -> None:
        self._cat, self._reader = catalog, reader

    def decompose(self, tree: RcaTreeSpec, current: Period, baseline: Period) -> list[ComponentContribution]:
        if tree.decomposition is None:
            return []
        root = self._cat.metric(tree.root_metric)
        self._reader.prefetch((self._cat.metric(m), [], p) for m in [tree.root_metric, *tree.decomposition.components] for p in (current, baseline))
        g1, g0 = self._reader.value(root, current), self._reader.value(root, baseline)
        if not g1 or not g0 or g1 <= 0 or g0 <= 0 or g1 == g0:
            return []  # logarithm undefined or no change: nothing to attribute
        scale = (g1 - g0) / math.log(g1 / g0)  # logarithmic mean
        rows = []
        for cid in tree.decomposition.components:
            metric = self._cat.metric(cid)
            v1, v0 = self._reader.value(metric, current), self._reader.value(metric, baseline)
            if not v1 or not v0 or v1 <= 0 or v0 <= 0:
                continue
            rows.append(ComponentContribution(component=cid, title=metric.title, format=metric.format, baseline=v0, current=v1,
                                              rel=relative_change(v1, v0), contribution=scale * math.log(v1 / v0)))
        return sorted(rows, key=lambda r: -abs(r.contribution))
