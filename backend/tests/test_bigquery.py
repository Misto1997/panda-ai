import sqlglot

from app.core.enums import QueryMode, TimeGrain
from app.engines.bigquery_engine import BigQueryEngine
from app.engines.bigquery_sql import to_bigquery
from app.query.guard import SqlGuard
from app.query.ir import QueryIR


def _compile(container, **kw):
    ir = QueryIR(metrics=kw.pop("metrics", ["net_gmv"]), time_expr="last_30_days", **kw)
    return container.query_service.compiler.compile(ir, container.query_service.resolver, QueryMode.AUTO).sql


def test_week_trunc_is_date_trunc_monday(container):
    sql = to_bigquery(_compile(container, grain=TimeGrain.WEEK), "proj", "panda")
    assert "DATE_TRUNC(order_date, WEEK(MONDAY))" in sql and "TIMESTAMP_TRUNC" not in sql
    assert "`proj`.`panda`.`agg_sales_daily`" in sql


def test_month_day_trunc_and_cte_not_qualified(container):
    month = to_bigquery(_compile(container, grain=TimeGrain.MONTH), "proj", "panda")
    assert "DATE_TRUNC(order_date, MONTH)" in month
    sql = _compile(container, metrics=["net_gmv", "visits"], dimensions=["zone"])  # two tables -> WITH ... FULL OUTER JOIN
    out = to_bigquery(sql, "proj", "panda")
    assert "WITH sales AS" in out and "`proj`.`panda`.`agg_traffic_state_daily`" in out
    sqlglot.parse_one(out, read="bigquery")  # valid BigQuery syntax
    assert "`panda`.`sales`" not in out  # CTE names stay bare


def test_ratio_cast_and_guard_accepts_compiler_sql(container):
    sql = _compile(container, metrics=["asp"], dimensions=["city"])
    assert "FLOAT64" in to_bigquery(sql, "p", "d")
    SqlGuard(container.catalog.physical_tables(), "bigquery", 100).check(sql)  # guard parses with engine.dialect


class _FakeRows(list):
    """Like google.cloud.bigquery RowIterator: iterable, and carries the schema."""
    schema = [type("F", (), {"name": "zone"}), type("F", (), {"name": "net_gmv"})]


class _FakeJob:
    total_bytes_processed, cache_hit = 1234, False
    schema = None  # regression: on real jobs this is unset; only the RowIterator returned by result() has the schema

    def result(self, timeout=None):
        return _FakeRows([type("R", (), {"values": lambda self: ("West", 1.5)})()])


class _FakeClient:
    def __init__(self):
        self.calls = []

    def query(self, sql, job_config=None, location=None):
        self.calls.append((sql, job_config, location))
        return _FakeJob()

    def close(self):
        pass


def test_engine_run_sets_cap_labels_stats():
    client = _FakeClient()
    eng = BigQueryEngine(client, "proj", "panda", "asia-southeast1", 10 * 1024**3)
    res = eng.run("SELECT zone, SUM(net_gmv) AS net_gmv FROM agg_sales_daily GROUP BY 1", 5)
    sql, cfg, loc = client.calls[0]
    assert cfg.maximum_bytes_billed == 10 * 1024**3 and cfg.labels == {"app": "panda-ai"} and loc == "asia-southeast1"
    assert res.columns == ["zone", "net_gmv"] and res.rows == [["West", 1.5]]
    assert res.stats == {"bytes_processed": 1234, "cache_hit": False}
    info = eng.dry_run("SELECT 1 FROM agg_sales_daily")
    assert info.ok and info.bytes_processed == 1234 and client.calls[1][1].dry_run


def test_bootstrap_export_and_layouts(tmp_path, settings):
    import duckdb

    from app.bootstrap.bq_load import LAYOUTS, export_parquet, load_config, user_tables
    from app.bootstrap.datagen import TABLES, generate_dataset

    db = tmp_path / "t.duckdb"
    counts = generate_dataset(db, settings.semantic_dir, rows=2000, days=20, end_date="2026-09-30")
    assert set(counts) == set(TABLES) and counts["fact_sales"] == 2000
    con = duckdb.connect(str(db), read_only=True)
    assert set(TABLES) <= set(user_tables(con))
    path = export_parquet(con, "agg_sales_daily", tmp_path / "pq")
    assert con.execute(f"SELECT COUNT(*) FROM read_parquet('{path}')").fetchone()[0] == counts["agg_sales_daily"]
    assert con.execute(f"SELECT typeof(order_date) FROM read_parquet('{path}') LIMIT 1").fetchone()[0] == "DATE"
    cfg = load_config(LAYOUTS["fact_sales"])
    assert cfg.time_partitioning.field == "order_date" and cfg.clustering_fields == ["marketplace", "zone"]
    assert cfg.write_disposition == "WRITE_TRUNCATE"
    con.close()


def test_turn_llm_budget():
    import pytest

    from app.core.errors import LlmBudgetExceededError
    from app.llm.base import Prompt
    from app.llm.budget import BudgetedLlm, _current, open_turn_budget

    class Inner:
        name = "x"
        def text(self, prompt, tier=None, context=None): return "ok"
    llm = BudgetedLlm(Inner())
    open_turn_budget(2)
    try:
        llm.text(Prompt("s", "u")); llm.text(Prompt("s", "u"))
        with pytest.raises(LlmBudgetExceededError):
            llm.text(Prompt("s", "u"))
    finally:
        _current.set(None)


# ---- regressions from the pre-deploy review ----
def test_division_is_safe_and_cte_names_are_case_insensitive():
    out = to_bigquery("WITH cur AS (SELECT SUM(a) AS a, SUM(b) AS b FROM agg_sales_daily) SELECT a / b AS r, a / 2 AS h FROM CUR", "p", "d")
    assert "SAFE_DIVIDE(a, b)" in out and "a / 2" in out          # variable denominators guarded, literal ones untouched
    assert "`d`.`CUR`" not in out and "FROM CUR" in out            # the CTE reference is not qualified as a physical table


def test_duckdb_hugeint_sums_are_exported_as_bigint(tmp_path):
    import duckdb, pyarrow.parquet as pq

    from app.bootstrap.bq_load import export_parquet

    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT 'a' AS k, SUM(x) AS n FROM (SELECT 3::INTEGER AS x UNION ALL SELECT 4) GROUP BY k")
    path = export_parquet(con, "t", tmp_path)
    assert str(pq.read_schema(path).field("n").type) == "int64"


def test_nan_and_infinity_become_null_for_json():
    from app.engines.duckdb_engine import to_jsonable
    assert [to_jsonable(v) for v in (float("nan"), float("inf"), -float("inf"), 1.5)] == [None, None, None, 1.5]
