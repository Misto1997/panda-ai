# PANDA AI

**PANDA** = Prompt-driven Analytics & Natural Data Access

Ask your data in plain English. PANDA AI writes **guarded SQL over a governed semantic layer** (validated, rewritten to rollups, dry-run, repaired), explains **why** a metric moved with a root-cause runbook, and stays fast on large tables through rollups and an intent-keyed semantic cache.

Built for the Google AI Builder Cup, theme **Future of Work & Enterprise Productivity**: analysts spend days answering "what happened and why"; PANDA AI does it in seconds, with numbers a finance team can trust.

> All code, data and semantic files are original and synthetic ("Acme Retail"). Nothing derives from any employer system.

## What it does

| Capability | How |
|---|---|
| **Ask** ("Net GMV by zone last 7 days") | Hybrid retrieval of governed metrics, dimensions, glossary and example SQL; Gemini writes SQL over logical tables; AST guard + engine dry-run + bounded repair; a rewriter picks rollup or raw tables; if generation fails, a deterministic IR compiler answers |
| **Investigate** ("Why did visits drop?") | Runbook-driven RCA: exact decomposition, segment drill-down (zone, region, state, city), 4-5 hypothesis tests per runbook, preflight data checks. The LLM only narrates computed facts |
| **Learn** ("What is BU visits?") | Hybrid retrieval over metrics, dimensions, glossary and runbooks |
| **Be fast** | Daily rollups when possible, raw tables otherwise; two-layer semantic cache (question to SQL, canonical intent derived from the SQL to result) |
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
Next.js UI + BFF --AG-UI events (SSE), A2UI answer surface, Vega-Lite--> FastAPI gateway --> LangGraph workflow --> Gemini (Agent Platform) | offline mock
   route -> plan (retrieve -> text-to-SQL -> guard -> dry-run -> repair | IR fallback) -> execute -> respond  |  rca | discover | help
   hybrid search (BM25/FTS + vectors, RRF) over semantic/  |  rewriter: logical -> rollup/raw  |  cache (plan, result)  |  RcaInvestigator
   engines: DuckDB (local/tests) | BigQuery (hosted)        state: AlloyDB/Postgres (pgvector, checkpoints, cache, quotas)
Hosting: Cloud Run (web, api, jobs) | Firebase Auth | Secret Manager | Vertex Gemini (location=global)
```

Full diagrams, class roles, retrieval, RCA maths, SSE and scale notes: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**. UI stack, BFF, AG-UI and A2UI: **[docs/FRONTEND_GUIDE.md](docs/FRONTEND_GUIDE.md)**. Deploying to Google Cloud: **[docs/GCP_SETUP.md](docs/GCP_SETUP.md)**. Decisions, positioning, costs: **[docs/PHASE2_PLAN.md](docs/PHASE2_PLAN.md)**.

## Quick start

Requirements: Python 3.12, Node 20+. Docker is optional.

```bash
make setup     # venv + npm install
make data      # 20M synthetic orders into backend/data/panda.duckdb (~20 s)
make api       # gateway on http://localhost:8000
make web       # UI on http://localhost:3000   (second terminal)
make test      # backend tests (79)
make bench     # golden questions through the full graph
```

Speed demo: tick **Force raw table scan** (skip the rollup) or **Bypass semantic cache** and compare the query-time chips; repeat a question without bypassing to see a cache hit.

## Tracing and debugging

Full guide (logs, verifying the index, BigQuery and database checks, auth, quota, cold starts, cost): **[docs/DEBUGGING.md](docs/DEBUGGING.md)**. Quick self-check: `make doctor` locally, `make gcp-diagnose` on Cloud Run.

```bash
make ask Q="why did visits drop in the last 14 days?"            # live step trace in the terminal
make ask Q="net gmv by zone last 7 days" DEBUG=1                 # + DEBUG logs, generated SQL, model output
make api-debug                                                    # server with DEBUG logs and payloads
```
Every HTTP request carries an `X-Request-Id` that appears on each log line. Expand "N steps" under an answer in the UI for per-step timings and cache hits. Optional LangSmith tracing: set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`. More in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#9-tracing-and-debugging).

## Configuration

**Profiles:** `config/profiles/local.yaml` (offline defaults) and `prod.yaml` (full production suite, enforced at startup); pick with `PANDA_PROFILE`, override any key with an env var, inspect with `make config`. Local and production differ only by profile. Recipes (real Gemini, BigQuery, Postgres locally): **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)**.

Secrets and per-machine values go in `.env` (copy `.env.example`).

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

- `POST /api/chat` `{question, thread_id?, force_raw?, bypass_cache?}` returns an **AG-UI** event stream over SSE (`RUN_STARTED`, `STEP_*`, `TEXT_MESSAGE_*`, `ACTIVITY_SNAPSHOT` with an A2UI surface, `CUSTOM panda.result`, `RUN_FINISHED` or `RUN_ERROR`). In `AUTH_MODE=firebase` send `Authorization: Bearer <Firebase ID token>`; 401/429 return JSON errors.
- `GET /api/me` (user and remaining daily quota), `GET /api/a2ui/catalog`.
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
| Semantic layer (13 metrics, 6 dimensions, glossary, 20 SQL examples, 4 RCA runbooks) | done |
| Text-to-SQL path, guard, rewriter, dry-run, repair, IR fallback, cache, RCA | done, tested offline (`make test`, 79 tests) |
| AG-UI stream, A2UI answer surface, Firebase sign-in UI, PANDA AI branding | done; sign-in not run end to end |
| BigQuery engine, bootstrap job, Dockerfiles, deploy scripts, budget kill-switch | written, **not yet run on GCP** |
| Gemini via Agent Platform | written, **not yet run** (model ids unverified) |
| AlloyDB/Postgres (pgvector, checkpointer, cache store, quotas) | written, **not yet run** |
| Golden benchmark | harness verified on the mock; real accuracy pending a Gemini run |
| Load behaviour | **not load tested** |

Known gaps: see "Unverified" in [AGENTS.md](AGENTS.md).

## License

Apache-2.0 (to be added before submission).
