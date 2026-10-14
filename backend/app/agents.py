"""LangGraph workflow: route -> {qna: plan -> execute -> respond | rca | discover | help}."""
from __future__ import annotations

import time
from functools import lru_cache
from typing import Annotated, Any, Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app import cache
from app.config import get_settings
from app.engine import get_engine
from app.llm import get_llm
from app.query.compiler import IRError, compile_ir
from app.query.guard import GuardError, check
from app.query.ir import QueryIR
from app.rca import run_rca
from app.semantic.catalog import load_catalog
from app.semantic.search import get_index
from app.viz import chart_for


class RouteDecision(BaseModel):
    route: Literal["qna", "rca", "discover", "help"] = Field(description=(
        "qna: a data question answerable with metrics; rca: why a metric moved; "
        "discover: what a metric/term means or what exists; help: greetings or product help"))
    reasoning: str = ""


class RcaRequest(BaseModel):
    metric: str = Field(description="Metric id whose movement should be explained")
    time_expr: str = Field(default="last_14_days", description="Period to explain, same grammar as QueryIR.time_expr")


class State(TypedDict, total=False):
    question: str
    options: dict
    route: str
    ir: dict
    last_ir: dict
    ir_source: str
    docs: list[str]
    compiled: dict
    result: dict
    response: dict
    trace: Annotated[list[dict], lambda _old, new: new]  # per-node trace, replaced not accumulated


def _hints(q: str, last_ir: dict | None) -> dict:
    cat = load_catalog()
    return {"question": q, "last_ir": last_ir, "catalog": {
        "metrics": [{"id": m.id, "names": [m.id.replace("_", " "), m.title, *m.aliases]} for m in cat.metrics.values()],
        "dimensions": [{"id": d.id, "names": [d.id.replace("_", " "), d.title, *d.aliases], "values": d.values}
                       for d in cat.dimensions.values() if d.id != "date"]}}


def _context(docs) -> str:
    return "\n".join(f"[{d.kind}] {d.id}: {d.text}" for d in docs)


PLAN_SYS = """You translate business questions into a structured query intent (QueryIR) for an analytics semantic layer.
Rules: use ONLY metric and dimension ids that appear in the context. Never invent metrics. Names of dimension values
(e.g. West, android) become filters, not dimensions. 'by X' means group by X. Use grain only for trends over time.
If the question is a follow-up, modify the previous intent instead of starting over. Default time_expr is last_30_days.
Semantic layer context:
{ctx}
Previous intent (may be null): {last}"""


def route(s: State) -> dict:
    t = time.perf_counter()
    d = get_llm().structured(RouteDecision, "Classify the user's analytics request.", s["question"], _hints(s["question"], s.get("last_ir")))
    # reset per-turn fields: state is checkpointed per thread, only last_ir carries over
    return {"route": d.route, "response": None, "result": None, "compiled": None, "ir": None, "trace": [{"step": "route", "detail": f"{d.route}", "ms": _ms(t)}]}


def _ms(t: float) -> float:
    return round((time.perf_counter() - t) * 1000, 1)


def plan(s: State) -> dict:
    t, q = time.perf_counter(), s["question"]
    use_cache = cache.enabled() and not s["options"].get("bypass_cache")
    key = cache.norm_question(q) + "|" + str(sorted((s.get("last_ir") or {}).get("metrics", [])))
    if use_cache and (hit := cache.plans.get(key)):
        cache.stats["plan_hits"] += 1
        return {"ir": hit["ir"], "docs": hit["docs"], "ir_source": "cache",
                "trace": [{"step": "plan", "detail": "intent from semantic cache (LLM skipped)", "ms": _ms(t), "cache": "hit"}]}
    cache.stats["plan_misses"] += 1
    docs = get_index().search(q, k=8, kinds={"metric", "dimension", "glossary"})
    ir = get_llm().structured(QueryIR, PLAN_SYS.format(ctx=_context(docs), last=s.get("last_ir")), q, _hints(q, s.get("last_ir")))
    out = ir.model_dump()
    if use_cache and out["metrics"]:
        cache.plans.put(key, {"ir": out, "docs": [d.id for d in docs]})
    return {"ir": out, "docs": [d.id for d in docs], "ir_source": "llm",
            "trace": [{"step": "retrieve", "detail": f"{get_index().backend_name}: " + ", ".join(d.id for d in docs[:6]), "ms": 0},
                      {"step": "plan", "detail": f"metrics={out['metrics']} dims={out['dimensions']} time={out['time_expr']}", "ms": _ms(t)}]}


def execute(s: State) -> dict:
    t, cat, eng = time.perf_counter(), load_catalog(), get_engine()
    mode = "raw" if s["options"].get("force_raw") else "auto"
    ir = QueryIR(**s["ir"])
    try:
        c = compile_ir(ir, cat, eng.anchor(), mode)
        allowed = {x.raw for x in cat.tables.values()} | {x.rollup for x in cat.tables.values()}
        sql = check(c.sql, allowed, eng.dialect)
    except (IRError, GuardError) as e:
        return {"response": {"type": "error", "text": str(e), "meta": {"route": "qna"}},
                "trace": [{"step": "compile", "detail": f"rejected: {e}", "ms": _ms(t)}]}
    key = cache.ir_key(s["ir"], str(c.start), str(c.end), mode)
    use_cache = cache.enabled() and not s["options"].get("bypass_cache")
    if use_cache and (hit := cache.results.get(key)):
        cache.stats["result_hits"] += 1
        return {"compiled": {"sql": c.sql, "sources": c.sources, "start": str(c.start), "end": str(c.end)},
                "result": {**hit, "cache": "hit", "elapsed_ms": 0.1},
                "trace": [{"step": "execute", "detail": f"result from semantic cache ({len(hit['rows'])} rows)", "ms": _ms(t), "cache": "hit"}]}
    cache.stats["result_misses"] += 1
    r = eng.run(sql)
    res = {"columns": r.columns, "rows": r.rows, "elapsed_ms": round(r.elapsed_ms, 1), "cache": "miss" if use_cache else "off"}
    if use_cache:
        cache.results.put(key, {"columns": r.columns, "rows": r.rows, "engine_ms": round(r.elapsed_ms, 1)})
    return {"compiled": {"sql": c.sql, "sources": c.sources, "start": str(c.start), "end": str(c.end)}, "result": res,
            "trace": [{"step": "compile", "detail": f"sources={c.sources} mode={mode}", "ms": 0},
                      {"step": "execute", "detail": f"{len(r.rows)} rows on {eng.name}", "ms": round(r.elapsed_ms, 1)}]}


def respond_qna(s: State) -> dict:
    if s.get("response"):
        return {}
    t, cat, eng = time.perf_counter(), load_catalog(), get_engine()
    r, c = s["result"], s["compiled"]
    formats = {m: cat.metrics[m].format for m in s["ir"]["metrics"]}
    titles = {m: cat.metrics[m].title for m in s["ir"]["metrics"]}
    text = get_llm().text(
        "You are a data analyst. Answer in 1-3 sentences using only the numbers provided. Bold key figures.",
        f"Question: {s['question']}\nColumns: {r['columns']}\nRows (max 15): {r['rows'][:15]}",
        {"task": "answer", "columns": r["columns"], "rows": r["rows"], "formats": formats, "titles": titles})
    meta = {"route": "qna", "engine": eng.name, "sources": c["sources"], "elapsed_ms": r["elapsed_ms"], "cache": r["cache"],
            "ir_source": s.get("ir_source"), "period": f"{c['start']} to {c['end']} (exclusive)", "llm": get_llm().name,
            "rows": len(r["rows"]), "docs": s.get("docs", [])}
    resp = {"type": "answer", "text": text, "table": {"columns": r["columns"], "rows": r["rows"], "formats": {**formats, "date": "date"},
            "titles": {**titles, **{d: cat.dimensions[d].title for d in s["ir"]["dimensions"]}, "date": "Date"}},
            "chart": chart_for(r["columns"], r["rows"], cat), "sql": c["sql"], "meta": meta}
    return {"response": resp, "last_ir": s["ir"], "trace": [{"step": "respond", "detail": "answer + chart", "ms": _ms(t)}]}


def rca(s: State) -> dict:
    t, cat, eng = time.perf_counter(), load_catalog(), get_engine()
    docs = get_index().search(s["question"], k=6, kinds={"metric", "rca_tree"})
    req = get_llm().structured(RcaRequest, f"Pick the metric and period to explain.\n{_context(docs)}", s["question"],
                               _hints(s["question"], s.get("last_ir")))
    if req.metric not in cat.metrics:
        return {"response": {"type": "error", "text": f"I can't investigate '{req.metric}'. Try GMV, orders, conversion rate or AOV.", "meta": {"route": "rca"}}}
    try:
        facts = run_rca(cat, eng.anchor(), req.metric, req.time_expr)
    except (IRError, ValueError) as e:
        return {"response": {"type": "error", "text": str(e), "meta": {"route": "rca"}}}
    narrative = get_llm().text(
        "You are a senior analyst writing a root-cause summary for an executive. 4-6 sentences. State the movement, the main "
        "driver and the segment, the confirmed hypothesis with its evidence, confidence, and one recommended next step. "
        "Use ONLY facts from the JSON. Do not speculate beyond confirmed hypotheses.",
        f"Facts JSON:\n{facts}", {"task": "rca", "facts": facts}, pro=True)
    rows = [[d["component"], d["baseline"], d["current"], d["rel"], d["contribution"]] for d in facts["decomposition"]]
    meta = {"route": "rca", "engine": eng.name, "llm": get_llm().name, "tree": facts["tree"], "queries": facts["queries_run"],
            "elapsed_ms": _ms(t), "docs": [d.id for d in docs], "cache": "off"}
    resp = {"type": "rca", "text": narrative, "rca": facts, "meta": meta, "sql": "\n\n".join(facts["sql_sample"])}
    return {"response": resp, "last_ir": {"metrics": [req.metric], "dimensions": [], "filters": [], "time_expr": req.time_expr, "grain": "none"},
            "trace": [{"step": "rca", "detail": f"tree={facts['tree']} {facts['queries_run']} queries", "ms": _ms(t)}]}


def discover(s: State) -> dict:
    t = time.perf_counter()
    docs = get_index().search(s["question"], k=5)
    text = get_llm().text("Answer using only the semantic layer context. Be concise and cite metric ids in backticks.",
                          f"Question: {s['question']}\nContext:\n{_context(docs)}",
                          {"task": "discover", "docs": [{"title": d.title, "text": d.text} for d in docs]})
    return {"response": {"type": "info", "text": text, "meta": {"route": "discover", "docs": [d.id for d in docs], "llm": get_llm().name,
                                                                 "backend": get_index().backend_name}},
            "trace": [{"step": "discover", "detail": ", ".join(d.id for d in docs), "ms": _ms(t)}]}


def help_(s: State) -> dict:
    cat = load_catalog()
    return {"response": {"type": "info", "meta": {"route": "help"}, "text": (
        "I answer questions about Acme Retail from governed metrics. Try:\n"
        "- **Ask**: \"GMV by region last 7 days\", \"daily conversion rate trend by channel\"\n"
        "- **Investigate**: \"Why did GMV drop in the last 14 days?\"\n"
        "- **Learn**: \"What is AOV?\"\n\nMetrics: " + ", ".join(f"`{m}`" for m in cat.metrics))}}


def _after_route(s: State) -> str:
    return {"qna": "plan", "rca": "rca", "discover": "discover", "help": "help"}[s["route"]]


def _after_execute(s: State) -> str:
    return END if s.get("response") else "respond"


def build_graph(checkpointer=None):
    g = StateGraph(State)
    for name, fn in [("route", route), ("plan", plan), ("execute", execute), ("respond", respond_qna), ("rca", rca),
                     ("discover", discover), ("help", help_)]:
        g.add_node(name, fn)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", _after_route, ["plan", "rca", "discover", "help"])
    g.add_edge("plan", "execute")
    g.add_conditional_edges("execute", _after_execute, ["respond", END])
    for n in ("respond", "rca", "discover", "help"):
        g.add_edge(n, END)
    return g.compile(checkpointer=checkpointer or MemorySaver())


@lru_cache
def get_checkpointer():
    url = get_settings().database_url
    if not url:
        return MemorySaver()
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool
    pool = ConnectionPool(url, max_size=10, kwargs={"autocommit": True, "prepare_threshold": 0}, open=True)
    saver = PostgresSaver(pool)
    saver.setup()
    return saver


@lru_cache
def get_graph():
    return build_graph(get_checkpointer())
