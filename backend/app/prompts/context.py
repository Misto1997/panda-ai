"""Builds the variable block of the SQL generation prompt from retrieved semantic documents."""
from __future__ import annotations

import json

from app.core.enums import DocKind
from app.query.logical import LogicalSchema
from app.query.period import PeriodResolver
from app.semantic.catalog import Catalog
from app.semantic.models import Doc

NAMED_PERIODS = ["yesterday", "last_7_days", "last_14_days", "last_30_days", "last_90_days", "this_week", "last_week", "this_month", "last_month"]
MAX_VALUES = 40


class SqlPromptContext:
    def __init__(self, catalog: Catalog, schema: LogicalSchema, resolver: PeriodResolver) -> None:
        self.cat, self.schema, self.resolver = catalog, schema, resolver

    def variables(self, docs: list[Doc], example_ids: list[str], last_sql: str | None, last_intent: dict | None) -> dict[str, str]:
        return {"schema": self.schema.describe(self.cat), "anchor": str(self.resolver.anchor), "periods": self._periods(),
                "context": self._context(docs), "examples": self._examples(example_ids),
                "last_sql": last_sql or "null", "last_intent": json.dumps(last_intent) if last_intent else "null"}

    def _periods(self) -> str:
        out = []
        for name in NAMED_PERIODS:
            p = self.resolver.resolve(name)
            out.append(f"- {name}: {p.start} to {p.end}")
        return "\n".join(out)

    def _context(self, docs: list[Doc]) -> str:
        lines: list[str] = []
        for d in docs:
            if d.kind == DocKind.METRIC and d.id in self.cat.metrics:
                m = self.cat.metrics[d.id]
                formula = m.expr if not m.is_ratio else f"({m.numerator}) / NULLIF({m.denominator}, 0)"
                lines.append(f"[metric] {m.id} ({m.title}; also {', '.join(m.aliases) or 'none'}) on table {m.table}: {formula}. "
                             f"{m.description} Valid dimensions: {', '.join(self.cat.dimension(x).column for x in m.dimensions)}.")
            elif d.kind == DocKind.DIMENSION and d.id in self.cat.dimensions:
                dim = self.cat.dimensions[d.id]
                values = ", ".join(dim.values[:MAX_VALUES]) + (" ..." if len(dim.values) > MAX_VALUES else "")
                lines.append(f"[dimension] column {dim.column} (tables: {', '.join(dim.tables)}; also {', '.join(dim.aliases) or 'none'}). Values: {values}")
            elif d.kind == DocKind.GLOSSARY:
                lines.append(f"[glossary] {d.text}")
        return "\n".join(lines) or "(none retrieved)"

    def _examples(self, example_ids: list[str]) -> str:
        blocks = []
        for i in example_ids:
            ex = self.cat.examples[i]
            blocks.append(f"Q: {ex.question}\nSQL: {' '.join(ex.sql.split())}")
        return "\n\n".join(blocks) or "(none)"
