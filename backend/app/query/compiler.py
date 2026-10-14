"""Compile a QueryIR to SQL using only governed definitions from the semantic layer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.query.ir import QueryIR
from app.query.timeutil import resolve
from app.semantic.catalog import Catalog, Metric


class IRError(ValueError):
    """User-facing: the question cannot be answered with the governed semantic layer."""


@dataclass
class Compiled:
    sql: str
    sources: dict[str, str]  # logical table -> physical table used
    columns: list[str]
    start: date
    end: date


def metric_expr(m: Metric) -> str:
    return m.expr if not m.is_ratio else f"CAST({m.numerator} AS DOUBLE) / NULLIF({m.denominator}, 0)"


def validate(ir: QueryIR, cat: Catalog) -> None:
    if not ir.metrics:
        raise IRError("No metric identified. Ask about a metric such as GMV, orders, AOV or conversion rate.")
    for mid in ir.metrics:
        if mid not in cat.metrics:
            raise IRError(f"Unknown metric '{mid}'.")
    for d in ir.dimensions + [f.dim for f in ir.filters]:
        if d not in cat.dimensions or d == "date":
            raise IRError(f"Unknown dimension '{d}'.")
        for mid in ir.metrics:
            if d not in cat.metrics[mid].dimensions:
                raise IRError(f"Metric '{mid}' cannot be sliced by '{d}'. Available: {', '.join(cat.metrics[mid].dimensions)}.")
    for f in ir.filters:
        known = {v.lower(): v for v in cat.dimensions[f.dim].values}
        bad = [v for v in f.values if known and v.lower() not in known]
        if bad:
            raise IRError(f"Unknown value(s) {bad} for {f.dim}. Valid: {', '.join(known.values())}.")
        f.values = [known.get(v.lower(), v) for v in f.values] if known else f.values
    if ir.order_by and ir.order_by not in ir.metrics:
        ir.order_by = None


def _lit(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


def compile_ir(ir: QueryIR, cat: Catalog, anchor: date, mode: str = "auto",
               select_parts: bool = False) -> Compiled:
    """mode: auto (rollup when possible) | raw (force raw fact tables).
    select_parts: emit numerator/denominator columns for ratio metrics (used by RCA)."""
    validate(ir, cat)
    start, end = resolve(ir.time_expr, anchor)
    dims = list(ir.dimensions)
    needed = set(dims) | {f.dim for f in ir.filters}

    by_table: dict[str, list[Metric]] = {}
    for mid in ir.metrics:
        by_table.setdefault(cat.metrics[mid].table, []).append(cat.metrics[mid])

    ctes, sources, outcols = [], {}, ([ "date"] if ir.grain != "none" else []) + dims
    for tid, metrics in by_table.items():
        t = cat.tables[tid]
        physical = t.rollup if (mode == "auto" and needed <= set(t.rollup_dimensions)) else t.raw
        sources[tid] = physical
        tc = t.time_column
        sel, grp = [], []
        if ir.grain != "none":
            sel.append(f"DATE_TRUNC('{ir.grain}', {tc}) AS date")
            grp.append("1")
        for d in dims:
            sel.append(cat.dimensions[d].column)
        grp += [str(i + 1 + (1 if ir.grain != "none" else 0)) for i in range(len(dims))]
        for m in metrics:
            if select_parts and m.is_ratio:
                sel += [f"{m.numerator} AS {m.id}__num", f"{m.denominator} AS {m.id}__den"]
                outcols += [f"{m.id}__num", f"{m.id}__den"]
            else:
                sel.append(f"{metric_expr(m)} AS {m.id}")
                outcols.append(m.id)
        where = [f"{tc} >= DATE '{start}'", f"{tc} < DATE '{end}'"]
        for f in ir.filters:
            col = cat.dimensions[f.dim].column
            where.append(f"{col} {'NOT ' if f.negate else ''}IN ({', '.join(_lit(v) for v in f.values)})")
        ctes.append((tid, f"SELECT {', '.join(sel)} FROM {physical} WHERE {' AND '.join(where)}"
                          + (f" GROUP BY {', '.join(grp)}" if grp else "")))

    keys = (["date"] if ir.grain != "none" else []) + dims
    if len(ctes) == 1:
        body = ctes[0][1]
    else:
        with_ = ", ".join(f"{tid} AS ({q})" for tid, q in ctes)
        first = ctes[0][0]
        joins = "".join(
            f" FULL OUTER JOIN {tid} USING ({', '.join(keys)})" if keys else f" CROSS JOIN {tid}"
            for tid, _ in ctes[1:])
        body = f"WITH {with_} SELECT * FROM {first}{joins}"
    order = ""
    if select_parts:
        pass
    elif ir.order_by:
        order = f" ORDER BY {ir.order_by} {'DESC' if ir.order_desc else 'ASC'}"
    elif ir.grain != "none":
        order = " ORDER BY date"
    elif dims and ir.metrics:
        order = f" ORDER BY {ir.metrics[0]} DESC"
    sql = f"SELECT * FROM ({body}) q{order}"
    return Compiled(sql, sources, outcols, start, end)
