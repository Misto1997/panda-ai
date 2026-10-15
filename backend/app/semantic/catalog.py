from __future__ import annotations

from dataclasses import dataclass, field

from app.core.errors import CatalogError, QueryValidationError
from app.semantic.models import (CheckSpec, DimensionSpec, Doc, MetricSpec, PolicySpec, RcaTreeSpec, TableSpec)


@dataclass
class Catalog:
    metrics: dict[str, MetricSpec] = field(default_factory=dict)
    dimensions: dict[str, DimensionSpec] = field(default_factory=dict)
    tables: dict[str, TableSpec] = field(default_factory=dict)
    trees: dict[str, RcaTreeSpec] = field(default_factory=dict)
    checks: dict[str, CheckSpec] = field(default_factory=dict)
    policies: dict[str, PolicySpec] = field(default_factory=dict)
    docs: list[Doc] = field(default_factory=list)

    def metric(self, metric_id: str) -> MetricSpec:
        try:
            return self.metrics[metric_id]
        except KeyError:
            raise QueryValidationError(f"Unknown metric '{metric_id}'.") from None

    def dimension(self, dim_id: str) -> DimensionSpec:
        try:
            return self.dimensions[dim_id]
        except KeyError:
            raise QueryValidationError(f"Unknown dimension '{dim_id}'.") from None

    def tree_for(self, metric_id: str) -> RcaTreeSpec | None:
        return next((t for t in self.trees.values() if t.root_metric == metric_id), None)

    def anchor_table(self) -> TableSpec:
        anchors = [t for t in self.tables.values() if t.anchor]
        if len(anchors) != 1:
            raise CatalogError("exactly one table must set `anchor: true`")
        return anchors[0]

    def physical_tables(self) -> set[str]:
        return {name for t in self.tables.values() for name in (t.raw, t.rollup)}

    def validate_references(self) -> None:
        """Cross-file integrity: every id a file points to must exist."""
        errs: list[str] = []
        for m in self.metrics.values():
            if m.table not in self.tables:
                errs.append(f"metric {m.id}: unknown table {m.table}")
            errs += [f"metric {m.id}: unknown dimension {d}" for d in m.dimensions if d not in self.dimensions]
        for t in self.tables.values():
            errs += [f"table {t.id}: unknown rollup dimension {d}" for d in t.rollup_dimensions if d not in self.dimensions]
        for tree in self.trees.values():
            refs = [tree.root_metric, *(tree.decomposition.components if tree.decomposition else [])]
            for h in tree.hypotheses:
                refs += [x for x in (h.metric, h.other_metric) if x]
                if h.dimension and h.dimension not in self.dimensions:
                    errs.append(f"tree {tree.id}/{h.id}: unknown dimension {h.dimension}")
            errs += [f"tree {tree.id}: unknown metric {m}" for m in refs if m not in self.metrics]
            errs += [f"tree {tree.id}: unknown check {c}" for c in tree.preflight if c not in self.checks]
            errs += [f"tree {tree.id}: unknown dimension {d}" for d in [*tree.drill_dimensions, *tree.marginal_dimensions] if d not in self.dimensions]
            if tree.policy not in self.policies:
                errs.append(f"tree {tree.id}: unknown policy {tree.policy}")
        for c in self.checks.values():
            if c.metric and c.metric not in self.metrics:
                errs.append(f"check {c.id}: unknown metric {c.metric}")
        self.anchor_table()
        if errs:
            raise CatalogError("semantic layer is inconsistent:\n  " + "\n  ".join(errs))
