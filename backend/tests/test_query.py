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


# ---------------------------------------------------------------------------------------------------------------------
# Text-to-SQL: logical guard, rewriter, normaliser, cache stores, planner flow, semantic examples, rollup/raw invariants
# ---------------------------------------------------------------------------------------------------------------------
import dataclasses

from app.agents.contracts import SqlDraft
from app.agents.deps import NodeDependencies
from app.agents.nodes.planner import SqlPlannerNode
from app.cache.semantic_cache import SemanticCache
from app.cache.store import CacheStore, MemoryCacheStore
from app.core.enums import CacheLayer, QueryPath
from app.llm.mock import MockLlm
from app.prompts.registry import PROMPTS

WINDOW = "order_date >= DATE '2026-09-24' AND order_date < DATE '2026-10-01'"


def sales_by(dim_sql: str, extra: str = "") -> str:
    return f"SELECT {dim_sql}, SUM(net_gmv) AS net_gmv FROM sales WHERE {WINDOW} {extra} GROUP BY 1"


@pytest.mark.parametrize("sql, fragment", [
    (f"SELECT * FROM sales WHERE {WINDOW}", "SELECT \\*"),
    ("SELECT zone, SUM(net_gmv) FROM secrets GROUP BY zone", "Unknown table"),
    ("SELECT zone, SUM(revenue) FROM sales GROUP BY zone", "could not be resolved"),
    ("SELECT zone, net_gmv FROM sales", "SUM"),                                   # bare measure
    ("SELECT zone, AVG(net_gmv) FROM sales GROUP BY zone", "SUM"),                # AVG of a measure differs between rollup and raw
    ("SELECT COUNT(*) FROM sales", "COUNT"),
    ("SELECT SUM(net_gmv) FROM read_csv('/etc/passwd')", "table functions"),
    ("SELECT SUM(net_gmv) FROM main.sales", "schema-qualified"),
    ("SELECT SUM(net_gmv) FROM sales; SELECT 1", "Exactly one"),
    ("DROP TABLE sales", "Only a single SELECT"),
    ("SELECT zone, SUM(pg_sleep(5)) FROM sales GROUP BY zone", "not allowed"),
    ("SELECT SUM(net_gmv) FROM sales a JOIN traffic b ON a.zone = b.zone JOIN bu_traffic c ON a.zone = c.zone "
     "JOIN sales d ON a.zone = d.zone JOIN sales e ON a.zone = e.zone", "Too many joins"),
    ("SELECT SUM(net_gmv) FROM sales a JOIN (SELECT zone FROM traffic) b ON a.zone = b.zone", "subqueries"),
    ("SELECT zone FROM sales a JOIN traffic b ON a.zone = b.zone", "could not be resolved"),  # ambiguous column
])
def test_logical_guard_rejects_with_repairable_message(container, sql, fragment):
    with pytest.raises(GuardViolationError, match=fragment):
        container.query_service.logical_guard.validate(sql)


def test_rewriter_picks_rollup_raw_and_honours_force_raw(container):
    svc = container.query_service
    assert svc.prepare_sql(sales_by("zone")).sources == {"sales": "agg_sales_daily"}
    assert svc.prepare_sql(sales_by("city")).sources == {"sales": "fact_sales"}            # city is not in the rollup
    assert svc.prepare_sql(sales_by("zone"), QueryMode.RAW).sources == {"sales": "fact_sales"}
    visits = "SELECT marketplace, SUM(visits) AS visits FROM traffic WHERE visit_date >= DATE '2026-09-24' GROUP BY 1"
    assert svc.prepare_sql(visits).sources == {"traffic": "agg_traffic_state_daily"}
    # each reference of a multi-table statement is decided on its own columns
    both = (f"WITH a AS (SELECT zone, SUM(net_gmv) AS g FROM sales WHERE {WINDOW} GROUP BY 1), "
            f"b AS (SELECT city, SUM(visits) AS v FROM traffic GROUP BY 1) SELECT a.zone, a.g FROM a")
    assert svc.prepare_sql(both).sources == {"sales": "agg_sales_daily", "traffic": "agg_traffic_city_daily"}


def test_prepared_sql_is_physical_capped_and_aliased(container):
    p = container.query_service.prepare_sql(f"SELECT sales.zone, SUM(sales.net_gmv) AS net_gmv FROM sales WHERE {WINDOW} GROUP BY 1")
    assert "agg_sales_daily AS sales" in p.physical_sql and p.physical_sql.endswith("LIMIT 500")
    assert "LIMIT 3" in container.query_service.prepare_sql(sales_by("zone", "ORDER BY 2 DESC LIMIT 3")).physical_sql.replace("500", "")


def test_normaliser_gives_equivalent_sql_one_cache_key(container):
    svc = container.query_service
    a = svc.prepare_sql(sales_by("zone"))
    b = svc.prepare_sql(f"select zone, sum(net_gmv) as net_gmv from sales where order_date < DATE '2026-10-01' and order_date >= DATE '2026-09-24' group by zone")
    assert a.intent.exact and b.intent.exact and a.intent.ir.time_expr == "last_7_days"
    assert SemanticCache.intent_key(a.intent, QueryMode.AUTO) == SemanticCache.intent_key(b.intent, QueryMode.AUTO)
    assert SemanticCache.intent_key(a.intent, QueryMode.AUTO) != SemanticCache.intent_key(a.intent, QueryMode.RAW)
    renamed = svc.prepare_sql(f"SELECT zone, SUM(net_gmv) AS revenue FROM sales WHERE {WINDOW} GROUP BY zone")
    assert not renamed.intent.exact  # different column names must not share an entry with the canonical shape
    # and the IR compiler path shares the entry with the exact SQL path
    ir = QueryIR(metrics=["net_gmv"], dimensions=["zone"], time_expr="last_7_days")
    assert SemanticCache.result_key(ir, svc.resolver.resolve("last_7_days"), QueryMode.AUTO) == SemanticCache.intent_key(a.intent, QueryMode.AUTO)


def test_normaliser_extracts_intent_and_degrades_to_fingerprint(container):
    svc = container.query_service
    sql = ("SELECT DATE_TRUNC('week', order_date) AS date, marketplace, SUM(net_gmv) / NULLIF(SUM(net_units), 0) AS asp FROM sales "
           "WHERE order_date >= DATE '2026-09-01' AND order_date < DATE '2026-10-01' AND zone IN ('South', 'West') AND business_unit <> 'Grocery' GROUP BY 1, 2 ORDER BY asp DESC LIMIT 4")
    ir = svc.prepare_sql(sql).intent.ir
    assert (ir.metrics, ir.dimensions, ir.grain.value, ir.time_expr, ir.order_by, ir.limit) == (["asp"], ["marketplace"], "week", "last_30_days", "asp", 4)
    assert {(f.dim, tuple(f.values), f.negate) for f in ir.filters} == {("zone", ("South", "West"), False), ("business_unit", ("Grocery",), True)}
    odd = svc.prepare_sql(f"SELECT zone, SUM(net_gmv) * 2 AS doubled FROM sales WHERE {WINDOW} GROUP BY zone").intent  # no governed metric
    assert odd.ir is None and not odd.exact and len(odd.fingerprint) == 40


def test_every_semantic_example_passes_guard_rewriter_and_runs(container):
    svc = container.query_service
    assert len(container.catalog.examples) >= 15
    for ex in container.catalog.examples.values():
        prepared = svc.prepare_sql(ex.sql)
        assert svc.dry_run(prepared).ok, ex.id
        assert svc.execute_sql(prepared, use_cache=False).result.rows, ex.id


@pytest.mark.parametrize("table, time_col, measures, dims", [
    ("sales", "order_date", "SUM(orders) AS o, SUM(gross_units) AS gu, SUM(net_units) AS nu, SUM(gross_gmv) AS gg, SUM(net_gmv) AS ng", ["zone", "region", "state", "marketplace", "business_unit"]),
    ("traffic", "visit_date", "SUM(visits) AS v, SUM(orders) AS o", ["zone", "region", "state", "marketplace"]),
    ("bu_traffic", "visit_date", "SUM(bu_visits) AS v, SUM(orders) AS o", ["state", "marketplace", "business_unit"]),
])
def test_rollup_and_raw_agree_for_shared_dimensions(container, table, time_col, measures, dims):
    svc = container.query_service
    for dim in dims:
        sql = f"SELECT {dim}, {measures} FROM {table} WHERE {time_col} >= DATE '2026-09-01' AND {time_col} < DATE '2026-10-01' GROUP BY 1"
        auto, raw = svc.prepare_sql(sql), svc.prepare_sql(sql, QueryMode.RAW)
        if container.catalog.tables[table].raw != container.catalog.tables[table].rollup:  # bu_traffic has a single physical table
            assert auto.sources != raw.sources, dim
        a, r = (sorted(svc.execute_sql(p, use_cache=False).result.rows) for p in (auto, raw))
        assert len(a) == len(r) and all(x[0] == y[0] and x[1:] == pytest.approx(y[1:], rel=1e-9) for x, y in zip(a, r)), dim


# ---- cache stores ----
class FlakyStore:
    """A store whose backend is down: every call raises."""
    name = "flaky"

    def get(self, layer, key): raise ConnectionError("down")
    def put(self, layer, key, value): raise ConnectionError("down")
    def size(self, layer): return 0
    def clear(self): pass
    def close(self): pass


def test_cache_store_interface_and_failure_tolerance(settings):
    mem = MemoryCacheStore(ttl_s=60, max_entries=2)
    assert isinstance(mem, CacheStore)
    for k in "abc":
        mem.put(CacheLayer.RESULT, k, {"v": k})
    assert mem.get(CacheLayer.RESULT, "a") is None and mem.get(CacheLayer.RESULT, "c") == {"v": "c"}  # LRU eviction, per layer
    assert mem.get(CacheLayer.PLAN, "c") is None and mem.size(CacheLayer.RESULT) == 2
    expired = MemoryCacheStore(ttl_s=-1, max_entries=2)
    expired.put(CacheLayer.PLAN, "x", {})
    assert expired.get(CacheLayer.PLAN, "x") is None
    cache = SemanticCache(settings, FlakyStore())  # an outage is a miss, never an exception
    cache.put_plan("k", {"sql": "x"})
    assert cache.get_plan("k") is None and cache.stats()["plan_misses"] == 1


# ---- planner: generate -> guard -> dry-run -> repair -> fallback ----
class ScriptedLlm(MockLlm):
    """Returns queued SQL drafts (the last one repeats) and records every SQL prompt; everything else behaves like the mock."""

    def __init__(self, *sqls: str):
        self.sqls, self.prompts, self.calls = list(sqls), [], 0

    def structured(self, schema, prompt, context=None):
        if schema is SqlDraft:
            self.prompts.append(prompt)
            sql = self.sqls[min(self.calls, len(self.sqls) - 1)]
            self.calls += 1
            return SqlDraft(sql=sql, rationale="scripted")
        return super().structured(schema, prompt, context)


def run_planner(container, llm, question="Net GMV by zone last 7 days", **settings_overrides):
    from app.llm.vocabulary import build_vocabulary
    deps = NodeDependencies(settings=container.settings.model_copy(update=settings_overrides), catalog=container.catalog, llm=llm,
                            prompts=PROMPTS, search=container.search, query_service=container.query_service, investigator=None,
                            cache=container.cache, charts=None, vocabulary=build_vocabulary(container.catalog))
    return SqlPlannerNode(deps)({"question": question, "options": {"bypass_cache": True}})


GOOD = sales_by("zone")


def test_planner_repairs_a_rejected_draft_with_the_error_as_feedback(container):
    llm = ScriptedLlm("SELECT zone, SUM(revenue) AS r FROM sales GROUP BY zone", GOOD)
    out = run_planner(container, llm)
    assert out["path"] == QueryPath.TEXT_TO_SQL and out["sql_attempts"] == 2 and out["sql"] == GOOD
    assert "could not be resolved" in llm.prompts[1].user and "revenue" in llm.prompts[1].user  # repair prompt carries the guard message
    assert out["ir"]["metrics"] == ["net_gmv"] and out["ir_source"] == "sql"


def test_planner_uses_engine_dry_run_errors_as_repair_feedback(container):
    llm = ScriptedLlm(f"SELECT zone, SUM(net_gmv) AS net_gmv FROM sales WHERE {WINDOW} GROUP BY region", GOOD)  # binds fine for sqlglot, not for the engine
    out = run_planner(container, llm)
    assert out["sql_attempts"] == 2 and "engine rejected" in llm.prompts[1].user and "agg_sales_daily" not in llm.prompts[1].user


def test_planner_falls_back_to_ir_after_exhausting_repairs(container):
    llm = ScriptedLlm("SELECT * FROM sales")
    out = run_planner(container, llm, sql_max_repairs=1)
    assert out["path"] == QueryPath.IR_FALLBACK and out["sql"] is None and out["sql_attempts"] == 2 and llm.calls == 2
    assert out["ir"]["metrics"] == ["net_gmv"]  # filled by the (mock) IR planner and compiled by code


def test_planner_declined_question_is_a_user_facing_error(container):
    out = run_planner(container, ScriptedLlm(""), question="show me widgets")
    assert out["response"]["type"] == "error"


def test_end_to_end_meta_path_attempts_and_plan_cache(container):
    def ask(question, thread, **opts):
        return [u.response for u in container.runner.stream(question, thread, opts) if u.response][-1]
    container.cache.clear()
    first = ask("Net GMV by marketplace last 14 days", "t-path-1")
    assert first["meta"]["path"] == "text_to_sql" and first["meta"]["sql_attempts"] == 1 and first["meta"]["ir_source"] == "sql"
    again = ask("Net GMV by marketplace last 14 days", "t-path-2")  # new thread: same plan key, no LLM call
    assert again["meta"]["path"] == "cache" and again["meta"]["cache"] == "hit" and again["table"]["rows"] == first["table"]["rows"]
    raw = ask("Net GMV by marketplace last 14 days", "t-path-3", force_raw=True)
    assert raw["meta"]["sources"] == {"sales": "fact_sales"} and raw["meta"]["cache"] == "miss"  # forced raw never reuses the rollup entry
