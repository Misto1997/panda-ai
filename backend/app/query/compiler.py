"""Compiles a QueryIR into SQL using only governed definitions from the semantic layer."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import QueryMode, TimeGrain
from app.core.errors import QueryValidationError
from app.query.ir import QueryIR
from app.query.period import Period, PeriodResolver
from app.semantic.catalog import Catalog
from app.semantic.models import MetricSpec, TableSpec

DATE_ALIAS = "date"


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    sources: dict[str, str]  # logical table -> physical table used
    columns: list[str]
    period: Period


class QueryCompiler:
    def __init__(self, catalog: Catalog) -> None:
        self.cat = catalog

    # ---- public ----
    def compile(self, ir: QueryIR, resolver: PeriodResolver, mode: QueryMode = QueryMode.AUTO,
                split_ratios: bool = False) -> CompiledQuery:
        """split_ratios: emit numerator/denominator columns for ratio metrics instead of the ratio (used by RCA)."""
        self.validate(ir)
        period = resolver.resolve(ir.time_expr)
        needed = set(ir.dimensions) | {f.dim for f in ir.filters}
        keys = ([DATE_ALIAS] if ir.grain != TimeGrain.NONE else []) + list(ir.dimensions)

        ctes, sources, columns = [], {}, list(keys)
        for table_id, metrics in self._group_by_table(ir).items():
            table = self.cat.tables[table_id]
            physical = table.rollup if mode == QueryMode.AUTO and needed <= set(table.rollup_dimensions) else table.raw
            sources[table_id] = physical
            select, cols = self._select(ir, table, metrics, split_ratios)
            columns += cols
            ctes.append((table_id, self._table_query(ir, table, physical, period, select)))

        body = self._combine(ctes, keys)
        return CompiledQuery(f"SELECT * FROM ({body}) q{self._order(ir, split_ratios)}", sources, columns, period)

    def validate(self, ir: QueryIR) -> None:
        if not ir.metrics:
            raise QueryValidationError("No metric identified. Ask about a metric such as Net GMV, orders, ASP or visits.")
        for mid in ir.metrics:
            self.cat.metric(mid)
        for dim in [*ir.dimensions, *(f.dim for f in ir.filters)]:
            if dim == DATE_ALIAS:
                raise QueryValidationError("Use a time period or grain instead of the date dimension.")
            self.cat.dimension(dim)
            for mid in ir.metrics:
                allowed = self.cat.metric(mid).dimensions
                if dim not in allowed:
                    raise QueryValidationError(
                        f"{self.cat.metric(mid).title} cannot be sliced by {self.cat.dimension(dim).title}. "
                        f"Available: {', '.join(allowed)}.")
        for f in ir.filters:
            known = {v.lower(): v for v in self.cat.dimension(f.dim).values}
            bad = [v for v in f.values if known and v.lower() not in known]
            if bad:
                raise QueryValidationError(f"Unknown value(s) {bad} for {f.dim}. Examples: {', '.join(list(known.values())[:8])}.")
            if not f.values:
                raise QueryValidationError(f"Filter on {f.dim} has no values.")
            f.values = [known.get(v.lower(), v) for v in f.values] if known else f.values
        if ir.order_by and ir.order_by not in ir.metrics:
            ir.order_by = None  # ordering by a metric that is not selected is ignored, not an error

    # ---- building blocks ----
    @staticmethod
    def metric_sql(metric: MetricSpec) -> str:
        if not metric.is_ratio:
            return metric.expr
        return f"CAST({metric.numerator} AS DOUBLE) / NULLIF({metric.denominator}, 0)"

    def _group_by_table(self, ir: QueryIR) -> dict[str, list[MetricSpec]]:
        groups: dict[str, list[MetricSpec]] = {}
        for mid in dict.fromkeys(ir.metrics):
            metric = self.cat.metric(mid)
            groups.setdefault(metric.table, []).append(metric)
        return groups

    def _select(self, ir: QueryIR, table: TableSpec, metrics: list[MetricSpec], split: bool) -> tuple[list[str], list[str]]:
        select, cols = [], []
        if ir.grain != TimeGrain.NONE:
            select.append(f"DATE_TRUNC('{ir.grain.value}', {table.time_column}) AS {DATE_ALIAS}")
        select += [self.cat.dimension(d).column for d in ir.dimensions]
        for m in metrics:
            if split and m.is_ratio:
                select += [f"{m.numerator} AS {m.id}__num", f"{m.denominator} AS {m.id}__den"]
                cols += [f"{m.id}__num", f"{m.id}__den"]
            else:
                select.append(f"{self.metric_sql(m)} AS {m.id}")
                cols.append(m.id)
        return select, cols

    def _table_query(self, ir: QueryIR, table: TableSpec, physical: str, period: Period, select: list[str]) -> str:
        where = [f"{table.time_column} >= DATE '{period.start}'", f"{table.time_column} < DATE '{period.end}'"]
        for f in ir.filters:
            values = ", ".join(_literal(v) for v in f.values)
            where.append(f"{self.cat.dimension(f.dim).column} {'NOT ' if f.negate else ''}IN ({values})")
        n_keys = (1 if ir.grain != TimeGrain.NONE else 0) + len(ir.dimensions)
        group = f" GROUP BY {', '.join(str(i + 1) for i in range(n_keys))}" if n_keys else ""
        return f"SELECT {', '.join(select)} FROM {physical} WHERE {' AND '.join(where)}{group}"

    @staticmethod
    def _combine(ctes: list[tuple[str, str]], keys: list[str]) -> str:
        if len(ctes) == 1:
            return ctes[0][1]
        with_ = ", ".join(f"{name} AS ({query})" for name, query in ctes)
        first = ctes[0][0]
        joins = "".join(f" FULL OUTER JOIN {name} USING ({', '.join(keys)})" if keys else f" CROSS JOIN {name}"
                        for name, _ in ctes[1:])
        return f"WITH {with_} SELECT * FROM {first}{joins}"

    @staticmethod
    def _order(ir: QueryIR, split: bool) -> str:
        if split:
            return ""
        if ir.order_by:
            return f" ORDER BY {ir.order_by} {'DESC' if ir.order_desc else 'ASC'}"
        if ir.grain != TimeGrain.NONE:
            return f" ORDER BY {DATE_ALIAS}"
        if ir.dimensions:
            return f" ORDER BY {ir.metrics[0]} DESC"
        return ""


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
