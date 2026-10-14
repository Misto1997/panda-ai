"""PANDA query gateway: SSE chat endpoint over the LangGraph workflow."""
from __future__ import annotations

import json
import time
import uuid

from fastapi import FastAPI
from fastapi.concurrency import iterate_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import cache
from app.agents import get_graph
from app.config import get_settings
from app.engine import get_engine
from app.semantic.catalog import load_catalog
from app.semantic.search import get_index

app = FastAPI(title="PANDA gateway", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])

SUGGESTIONS = [
    "GMV by region for the last 7 days",
    "Daily conversion rate by channel last 14 days",
    "Why did GMV drop in the last 14 days?",
    "Average order value by category for android in West last 30 days",
    "What is checkout completion rate?",
]


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    thread_id: str | None = None
    force_raw: bool = False
    bypass_cache: bool = False


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/meta")
def meta() -> dict:
    s, cat, eng = get_settings(), load_catalog(), get_engine()
    return {
        "llm": s.llm_provider, "engine": eng.name, "search": get_index().backend_name, "anchor": str(eng.anchor()),
        "tables": {t: eng.row_count(t) for t in ("fact_orders", "agg_orders_daily", "agg_traffic_daily")},
        "metrics": [{"id": m.id, "title": m.title, "description": m.description} for m in cat.metrics.values()],
        "suggestions": SUGGESTIONS, "cache": cache.stats,
    }


@app.post("/api/cache/clear")
def clear_cache() -> dict:
    cache.clear()
    return {"cleared": True}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    thread = req.thread_id or uuid.uuid4().hex
    cfg = {"configurable": {"thread_id": thread}}
    state = {"question": req.question, "options": {"force_raw": req.force_raw, "bypass_cache": req.bypass_cache}}

    async def gen():
        t0 = time.perf_counter()
        yield _sse("run_started", {"thread_id": thread})
        final = None
        try:
            async for mode, chunk in _stream(state, cfg):
                for node, upd in chunk.items():
                    if not upd:
                        continue
                    for step in upd.get("trace") or []:
                        yield _sse("step", {"node": node, **step})
                    if upd.get("response"):
                        final = upd["response"]
        except Exception as e:  # surface as an error event, never a dropped stream
            yield _sse("error", {"message": f"{type(e).__name__}: {e}"})
            return
        if final:
            final.setdefault("meta", {})["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            yield _sse("result", final)
        yield _sse("run_finished", {"thread_id": thread})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _stream(state: dict, cfg: dict):
    graph = get_graph()
    async for item in iterate_in_threadpool(graph.stream(state, cfg, stream_mode=["updates"])):
        yield item
