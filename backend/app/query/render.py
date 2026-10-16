"""QueryIR -> logical SQL (the text-to-sql dialect: logical tables, SUM() of base measures, explicit date predicates).
Used by the offline mock LLM to emit the same kind of SQL a real model is asked to write, and by tests.
It deliberately does not validate dimensions against metrics: like a model, it can emit SQL the guard will reject."""
from __future__ import annotations

from app.core.enums import TimeGrain
from app.query.compiler import DATE_ALIAS, QueryCompiler, _literal
from app.query.ir import QueryIR
from app.query.period import PeriodResolver
from app.semantic.catalog import Catalog


class LogicalSqlRenderer:
    def __init__(self, catalog: Catalog, resolver: PeriodResolver) -> None:
        self.cat, self.resolver = catalog, resolver
        self._compiler = QueryCompiler(catalog)

    def render(self, ir: QueryIR) -> str:
        period = self.resolver.resolve(ir.time_expr)
        grain = ir.grain != TimeGrain.NONE
        keys = ([DATE_ALIAS] if grain else []) + [self.cat.dimension(d).column for d in ir.dimensions]
        groups = self._compiler._group_by_table(ir)

        blocks = []
        for table_id, metrics in groups.items():
            table = self.cat.tables[table_id]
            select = ([f"DATE_TRUNC('{ir.grain.value}', {table.time_column}) AS {DATE_ALIAS}"] if grain else [])
            select += [self.cat.dimension(d).column for d in ir.dimensions]
            select += [f"{self._metric(m)} AS {m.id}" for m in metrics]
            where = [f"{table.time_column} >= DATE '{period.start}'", f"{table.time_column} < DATE '{period.end}'"]
            where += [f"{self.cat.dimension(f.dim).column} {'NOT ' if f.negate else ''}IN ({', '.join(_literal(v) for v in f.values)})"
                      for f in ir.filters]
            group = f" GROUP BY {', '.join(str(i + 1) for i in range(len(keys)))}" if keys else ""
            blocks.append((table_id, f"SELECT {', '.join(select)} FROM {table_id} WHERE {' AND '.join(where)}{group}"))

        order = self._order(ir, keys)
        limit = f" LIMIT {ir.limit}" if ir.limit else ""
        if len(blocks) == 1:
            return blocks[0][1] + order + limit
        names = [f"{n}_agg" for n, _ in blocks]
        with_ = ", ".join(f"{name} AS ({query})" for name, (_, query) in zip(names, blocks))
        cols = ", ".join([*keys, *ir.metrics])
        joins = "".join(f" FULL OUTER JOIN {n} USING ({', '.join(keys)})" if keys else f" CROSS JOIN {n}" for n in names[1:])
        return f"WITH {with_} SELECT {cols} FROM {names[0]}{joins}{order}{limit}"

    @staticmethod
    def _metric(metric) -> str:
        return metric.expr if not metric.is_ratio else f"({metric.numerator}) / NULLIF({metric.denominator}, 0)"

    @staticmethod
    def _order(ir: QueryIR, keys: list[str]) -> str:
        if ir.order_by and ir.order_by in ir.metrics:
            return f" ORDER BY {ir.order_by} {'DESC' if ir.order_desc else 'ASC'}"
        if ir.grain != TimeGrain.NONE:
            return f" ORDER BY {DATE_ALIAS}"
        return f" ORDER BY {ir.metrics[0]} DESC" if ir.dimensions else ""
