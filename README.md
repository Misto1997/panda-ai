# PANDA: Prompt-driven Analytics & Natural Data Access

Ask your data in plain English. PANDA answers from **governed metrics** (the LLM never writes free-form SQL), explains **why** a metric moved with a root-cause runbook, and stays fast on large tables through rollups and a semantic cache.

Built for the Google AI Builder Cup, theme **Future of Work & Enterprise Productivity**: analysts spend days answering "what happened and why"; PANDA does it in seconds, with numbers a finance team can trust.

> All code, data and semantic files are original and synthetic ("Acme Retail"). Nothing derives from any employer system.

## What it does

| Capability | How |
|---|---|
| **Ask** ("Net GMV by zone last 7 days") | LLM extracts a structured intent (`QueryIR`) from retrieved semantic context; code compiles SQL from governed definitions; a guard validates it; the engine runs it |
| **Investigate** ("Why did visits drop?") | Runbook-driven RCA: exact decomposition, segment drill-down (zone, region, state, city), 4-5 hypothesis tests per runbook, preflight data checks. The LLM only narrates computed facts |
| **Learn** ("What is BU visits?") | Hybrid retrieval over metrics, dimensions, glossary and runbooks |
| **Be fast** | Daily rollups when possible, raw tables otherwise; two-layer semantic cache (question to intent, resolved intent to result) |
| **Follow-ups** | Per-thread memory: "and by marketplace?" modifies the previous intent |

## The demo domain

13 metrics (Net/Gross GMV, Net/Gross Units, Orders, ASP, Gross AOV, Net-to-Gross, Cancellation Rate, Visits, Conversion, BU Visits, BU Conversion) and 6 dimensions (Marketplace, Business Unit, Zone > Region > State > City). 20M synthetic orders with three planted problems, one per RCA runbook:

| Ask | Planted cause the RCA should find |
|---|---|
| "Why did Net GMV drop in the last 14 days?" | Cancellation spike in Acme Express x South |
| "Why did visits drop in the last 14 days?" | Visit-tracking loss in Acme Mall x East (orders unchanged, conversion rises artificially) |
| "Why did ASP drop in the last 14 days?" | Business-unit mix shift to Grocery in Acme Wholesale x North |
| "Why did conversion rate change?" | Same tracking loss, seen through the conversion denominator |

## Architecture

```
Next.js UI + BFF --SSE--> FastAPI gateway --> LangGraph workflow --> Gemini (or offline mock)
                                               route -> plan -> execute -> respond | rca | discover | help
                          hybrid search (BM25/FTS + vectors, RRF) over semantic/
                          QueryIR -> compiler -> guard -> cache -> engine (DuckDB | BigQuery*)
                          RcaInvestigator (decomposition, drill, hypotheses, checks)
```
\* BigQuery, Cloud Run, Vertex AI, Google login: phase 2.

Full diagrams, class roles, retrieval, RCA maths, SSE and scale notes: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**. UI stack, BFF and file-by-file guide: **[docs/FRONTEND_GUIDE.md](docs/FRONTEND_GUIDE.md)**.

## Quick start

Requirements: Python 3.12, Node 20+. Docker is optional.

```bash
make setup     # venv + npm install
make data      # 20M synthetic orders into backend/data/panda.duckdb (~20 s)
make api       # gateway on http://localhost:8000
make web       # UI on http://localhost:3000   (second terminal)
make test      # backend tests
```

Speed demo: tick **Force raw table scan** (skip the rollup) or **Bypass semantic cache** and compare the query-time chips; repeat a question without bypassing to see a cache hit.

## Tracing and debugging

```bash
make ask Q="why did visits drop in the last 14 days?"            # live step trace in the terminal
make ask Q="net gmv by zone last 7 days" DEBUG=1                 # + DEBUG logs, generated SQL, model output
make api-debug                                                    # server with DEBUG logs and payloads
```
Every HTTP request carries an `X-Request-Id` that appears on each log line. Expand "N steps" under an answer in the UI for per-step timings and cache hits. Optional LangSmith tracing: set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`. More in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#9-tracing-and-debugging).

## Configuration

Copy `.env.example` to `.env`.

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `mock` (default, offline) or `gemini` |
| `GOOGLE_API_KEY` | AI Studio key for `gemini`; for Vertex AI set `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` |
| `GEMINI_MODEL`, `GEMINI_PRO_MODEL`, `EMBEDDING_MODEL` | Model names (unverified defaults; check availability) |
| `ENGINE` | `duckdb` (BigQuery in phase 2) |
| `DATABASE_URL` | Optional Postgres: pgvector + full-text search and a Postgres LangGraph checkpointer. `make up`, then `make ingest` |
| `LOG_LEVEL`, `TRACE_PAYLOADS` | Logging verbosity; `TRACE_PAYLOADS` adds SQL and model output to DEBUG logs |
| `GATEWAY_URL` | Frontend: gateway address (default `http://localhost:8000`) |

## API

- `POST /api/chat` `{question, thread_id?, force_raw?, bypass_cache?}` returns an SSE stream: `run_started`, `step`*, `result`, `run_finished` (or `error`).
- `GET /api/meta` runtime info, metrics, suggestions, cache stats. `GET /health`, `GET /ready`.
- `POST /api/admin/cache/clear`, `GET /api/admin/cache/stats`.

## Repository layout

```
semantic/      Governed layer: metrics, dimensions, tables, glossary, rca/{trees,checks,policies}
backend/       app/ (core, semantic, search, llm, prompts, engines, query, cache, rca, agents, api), scripts/, tests/
frontend/      Next.js UI + BFF
docs/          ARCHITECTURE.md, FRONTEND_GUIDE.md
AGENTS.md      Orientation and rules for coding agents and new contributors
```

## Extending

- **Metric or runbook:** add a markdown file under `semantic/`; the loader validates cross-references at startup.
- **Engine, LLM, search backend, graph node, hypothesis type:** implement the port or subclass, register it. See the pattern table in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#8-patterns-and-where-to-extend).

## Status

| Area | State |
|---|---|
| Semantic layer, compiler, guard, cache, RCA (4 runbooks), workflow, gateway, UI | done, tested (`make test`, 33 tests) |
| Mock LLM end to end | verified |
| Gemini with real credentials | written, **not yet run** |
| Postgres / pgvector / Postgres checkpointer | written, **not yet run** |
| Load behaviour of the SSE gateway | **not load tested** |
| BigQuery engine, Cloud Run deploy, Google login and row-level scope, Gemma router, benchmark, deck, demo video | phase 2 and 3 |

Known gaps: no authentication on the gateway; cache and checkpointer are in-process unless `DATABASE_URL` is set; BigQuery date-truncation transpile needs care.

## License

Apache-2.0 (to be added before submission).
