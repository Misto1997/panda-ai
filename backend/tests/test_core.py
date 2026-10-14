import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.engine import get_engine
from app.query.compiler import IRError, compile_ir
from app.query.guard import GuardError, check
from app.query.ir import QueryIR
from app.query.timeutil import resolve
from app.rca import run_rca
from app.semantic.catalog import load_catalog
from app.semantic.search import rrf

cat = load_catalog()
ANCHOR = date(2026, 9, 30)


def test_time_resolution_half_open():
    assert resolve("yesterday", ANCHOR) == (date(2026, 9, 30), date(2026, 10, 1))
    assert resolve("last_7_days", ANCHOR) == (date(2026, 9, 24), date(2026, 10, 1))
    assert resolve("2026-09-01..2026-09-02", ANCHOR) == (date(2026, 9, 1), date(2026, 9, 3))


def test_compiler_uses_rollup_unless_forced_raw():
    ir = QueryIR(metrics=["gmv"], dimensions=["region"], time_expr="last_7_days")
    assert compile_ir(ir, cat, ANCHOR).sources == {"orders": "agg_orders_daily"}
    assert compile_ir(ir, cat, ANCHOR, "raw").sources == {"orders": "fact_orders"}


def test_compiler_rejects_ungoverned_requests():
    with pytest.raises(IRError):
        compile_ir(QueryIR(metrics=["conversion_rate"], dimensions=["category"]), cat, ANCHOR)  # traffic has no category
    with pytest.raises(IRError):
        compile_ir(QueryIR(metrics=["revenue_per_planet"]), cat, ANCHOR)


@pytest.mark.parametrize("sql", ["DROP TABLE fact_orders", "SELECT * FROM secrets", "SELECT 1; SELECT 2", "DELETE FROM fact_orders"])
def test_guard_blocks(sql):
    with pytest.raises(GuardError):
        check(sql, {"fact_orders"})


def test_guard_adds_limit():
    assert check("SELECT * FROM fact_orders", {"fact_orders"}).endswith("LIMIT 500")


def test_rrf_prefers_agreement():
    assert max(rrf([["a", "b"], ["b", "c"]]).items(), key=lambda kv: kv[1])[0] == "b"


def test_rca_finds_planted_anomaly():
    f = run_rca(cat, get_engine().anchor(), "gmv", "last_14_days")
    top = f["drill"]["cells"][0]
    assert top["segment"] == {"region": "West", "channel": "android"}
    assert f["decomposition"][0]["component"] == "conversion_rate"
    assert next(h for h in f["hypotheses"] if h["id"] == "h_checkout_failure")["status"] == "confirmed"
    assert sum(d["contribution"] for d in f["decomposition"]) == pytest.approx(f["current"]["value"] - f["baseline"]["value"], rel=1e-6)


def test_chat_stream_and_cache():
    from app.main import app
    c = TestClient(app)

    def ask(q, **kw):
        r = c.post("/api/chat", json={"question": q, **kw})
        events = [(b.split("\n")[0][7:], json.loads(b.split("\n")[1][6:])) for b in r.text.strip().split("\n\n")]
        return events, next(d for e, d in events if e == "result")

    c.post("/api/cache/clear")
    ev, res = ask("GMV by region last 7 days")
    assert [e for e, _ in ev][0] == "run_started" and ev[-1][0] == "run_finished"
    assert res["meta"]["cache"] == "miss" and len(res["table"]["rows"]) == 4
    assert ask("revenue split by region past 7 days")[1]["meta"]["cache"] == "hit"
    assert ask("GMV by region last 7 days", bypass_cache=True)[1]["meta"]["cache"] == "off"
