from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from app.core.errors import CatalogError, QueryValidationError
from app.semantic.models import (CheckSpec, DimensionSpec, Doc, ExampleSpec, MetricSpec, PolicySpec, RcaTreeSpec, TableSpec)
from app.semantic.models import LOGICAL_DIALECT


@dataclass
class Catalog:
    metrics: dict[str, MetricSpec] = field(default_factory=dict)
    dimensions: dict[str, DimensionSpec] = field(default_factory=dict)
    tables: dict[str, TableSpec] = field(default_factory=dict)
    trees: dict[str, RcaTreeSpec] = field(default_factory=dict)
    checks: dict[str, CheckSpec] = field(default_factory=dict)
    policies: dict[str, PolicySpec] = field(default_factory=dict)
    examples: dict[str, ExampleSpec] = field(default_factory=dict)
    docs: list[Doc] = field(default_factory=list)

    def metric(self, metric_id: str) -> MetricSpec:
        try:
            return self.metrics[metric_id]
        except KeyError:
            raise QueryValidationError(f"Unknown metric '{metric_id}'.") from None

    def find_metric(self, name: str) -> MetricSpec | None:
        """Resolve an id, title or alias (case/space/underscore-insensitive); None if unknown."""
        key = "".join(ch for ch in name.lower() if ch.isalnum())
        for m in self.metrics.values():
            if key in {"".join(ch for ch in n.lower() if ch.isalnum()) for n in (m.id, m.title, *m.aliases)}:
                return m
        return None

    def metrics_in(self, text: str) -> list[MetricSpec]:
        """Metrics named in free text (id, title or alias), in order of appearance; the longest name wins an overlap ('net gmv' over 'gmv')."""
        import re

        q, spans = text.lower(), []
        names = sorted(((n.lower().replace("_", " "), m) for m in self.metrics.values() for n in (m.id, m.title, *m.aliases)),
                       key=lambda nm: -len(nm[0]))
        for name, metric in names:
            for hit in re.finditer(rf"\b{re.escape(name)}s?\b", q):
                if not any(hit.start() < b and a < hit.end() for a, b, _ in spans):
                    spans.append((hit.start(), hit.end(), metric))
        seen: list[MetricSpec] = []
        for _, _, metric in sorted(spans, key=lambda s: s[0]):
            if metric not in seen:
                seen.append(metric)
        return seen

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

    def _example_errors(self, ex: ExampleSpec) -> list[str]:
        try:
            tree = sqlglot.parse_one(ex.sql, dialect=LOGICAL_DIALECT)
        except sqlglot.errors.ParseError as e:
            return [f"example {ex.id}: unparseable sql ({e})"]
        ctes = {c.alias for c in tree.find_all(exp.CTE)}
        unknown = {t.name for t in tree.find_all(exp.Table)} - ctes - set(self.tables)
        return [f"example {ex.id}: unknown table(s) {sorted(unknown)}"] if unknown else []

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
        for ex in self.examples.values():
            errs += self._example_errors(ex)
        for t in self.tables.values():
            if not t.measures:
                errs.append(f"table {t.id}: declare `measures` (additive columns of the logical table)")
        for c in self.checks.values():
            if c.metric and c.metric not in self.metrics:
                errs.append(f"check {c.id}: unknown metric {c.metric}")
        self.anchor_table()
        if errs:
            raise CatalogError("semantic layer is inconsistent:\n  " + "\n  ".join(errs))
