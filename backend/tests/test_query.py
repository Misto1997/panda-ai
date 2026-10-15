from datetime import date

import pytest

from app.core.enums import QueryMode, TimeGrain
from app.core.errors import GuardViolationError, QueryValidationError, UnsupportedTimeExpressionError
from app.query.guard import SqlGuard
from app.query.ir import Filter, QueryIR
from app.query.period import PeriodResolver

ANCHOR = date(2026, 9, 30)


def test_period_resolution_is_half_open():
    r = PeriodResolver(ANCHOR)
    assert (r.resolve("yesterday").start, r.resolve("yesterday").end) == (date(2026, 9, 30), date(2026, 10, 1))
    assert r.resolve("last_7_days").start == date(2026, 9, 24)
    assert r.resolve("2026-09-01..2026-09-02").end == date(2026, 9, 3)
    assert r.resolve("last_14_days").previous().end == r.resolve("last_14_days").start


@pytest.mark.parametrize("expr", ["next_year", "2026-09-05..2026-09-01", "last_0_days", "2026-13-01..2026-13-02"])
def test_period_rejects_bad_expressions(expr):
    with pytest.raises(UnsupportedTimeExpressionError):
        PeriodResolver(ANCHOR).resolve(expr)


def test_rollup_used_unless_dimension_missing_or_forced_raw(container):
    svc = container.query_service
    by_zone = QueryIR(metrics=["net_gmv"], dimensions=["zone"], time_expr="last_7_days")
    assert svc.compiler.compile(by_zone, svc.resolver).sources == {"sales": "agg_sales_daily"}
    assert svc.compiler.compile(by_zone, svc.resolver, QueryMode.RAW).sources == {"sales": "fact_sales"}
    by_city = QueryIR(metrics=["net_gmv"], dimensions=["city"], time_expr="last_7_days")
    assert svc.compiler.compile(by_city, svc.resolver).sources == {"sales": "fact_sales"}  # city is not in the rollup


def test_multi_table_query_joins_and_runs(container):
    ir = QueryIR(metrics=["net_gmv", "visits"], dimensions=["marketplace"], time_expr="last_7_days")
    out = container.query_service.execute(ir, use_cache=False)
    assert set(out.result.columns) == {"marketplace", "net_gmv", "visits"} and len(out.result.rows) == 3


def test_filter_values_are_normalised_and_weekly_grain_works(container):
    ir = QueryIR(metrics=["orders"], filters=[Filter(dim="zone", values=["south"])], grain=TimeGrain.WEEK, time_expr="last_30_days")
    out = container.query_service.execute(ir, use_cache=False)
    assert "zone IN ('South')" in out.compiled.sql and len(out.result.rows) >= 4


@pytest.mark.parametrize("ir, fragment", [
    (QueryIR(metrics=[]), "No metric"),
    (QueryIR(metrics=["nope"]), "Unknown metric"),
    (QueryIR(metrics=["visits"], dimensions=["business_unit"]), "cannot be sliced"),  # visits are not split by BU
    (QueryIR(metrics=["orders"], filters=[Filter(dim="zone", values=["Atlantis"])]), "Unknown value"),
])
def test_compiler_rejects_ungoverned_requests(container, ir, fragment):
    with pytest.raises(QueryValidationError, match=fragment):
        container.query_service.compiler.validate(ir)


@pytest.mark.parametrize("sql", ["DROP TABLE fact_sales", "SELECT * FROM secrets", "SELECT 1; SELECT 2", "DELETE FROM fact_sales", "not sql at all"])
def test_guard_blocks(sql):
    with pytest.raises(GuardViolationError):
        SqlGuard({"fact_sales"}, "duckdb", 500).check(sql)


def test_guard_caps_rows_and_allows_ctes():
    guard = SqlGuard({"fact_sales"}, "duckdb", 500)
    assert guard.check("WITH a AS (SELECT * FROM fact_sales) SELECT * FROM a").endswith("LIMIT 500")
