# PANDA: Prompt-driven Analytics & Natural Data Access

Ask your data in plain English. PANDA answers from **governed metrics** (the LLM never writes free-form SQL), explains **why** a metric moved with a root-cause runbook, and stays fast on large tables through rollups and a semantic cache.

Built for the Google AI Builder Cup, theme **Future of Work & Enterprise Productivity**: analysts spend days answering "what happened and why"; PANDA does it in seconds, with numbers a finance team can trust.

> All code, data and semantic files are original and synthetic ("Acme Retail"). Nothing derives from any employer system.

## What it does

| Capability | How |
|---|---|
| **Ask** ("GMV by region last 7 days") | LLM extracts a structured intent (`QueryIR`) using retrieved semantic context; code compiles SQL from governed definitions; a guard validates it; the engine runs it |
| **Investigate** ("Why did GMV drop?") | Runbook-driven RCA: exact log-ratio decomposition (traffic x conversion x AOV), segment drill-down, hypothesis tests (funnel walk, metric shift), preflight data checks. The LLM only narrates computed facts |
| **Learn** ("What is AOV?") | Hybrid retrieval over metrics, dimensions, glossary and runbooks |
| **Be fast** | Queries use a daily rollup when possible, raw tables otherwise; two-layer semantic cache (question to intent, resolved intent to result) |
| **Follow-ups** | Per-thread memory: "and by channel?" modifies the previous intent |

## Architecture

```
Browser: Next.js UI  --SSE-->  Next.js BFF (/api/chat)  -->  FastAPI gateway (/api/chat)
                                                                   |
                                                             LangGraph workflow
          route -> plan -> execute -> respond (data questions) | rca | discover | help
                     |         |
        hybrid search      QueryIR -> compiler -> guard -> engine (DuckDB | BigQuery*)
   (BM25/FTS + vectors, RRF)          semantic cache (question->IR, IR->result)
                     |
               semantic/  (markdown + YAML: metrics, dimensions, glossary, RCA runbooks)
```
\* BigQuery, Cloud Run, Vertex AI and Google login land in phase 2.

Design choices that matter:
- **Governed, not generative, SQL.** The model picks metrics/dimensions; the compiler owns SQL. The guard (sqlglot) allows only a single read-only SELECT on approved tables and caps rows.
- **Hybrid retrieval.** Lexical search handles ids and abbreviations; vectors handle paraphrase; reciprocal rank fusion merges them; matched metrics pull in their allowed dimensions.
- **Offline-capable.** `LLM_PROVIDER=mock` runs the whole pipeline with no credentials: development, tests and a safe demo fallback.
- **Pluggable engine.** DuckDB locally, BigQuery next; the production-scale story (rollups, materialized views) is the same.

## Repository layout

```
semantic/        Governed layer: metrics/, dimensions/, tables/, glossary/, rca/{trees,checks,policies}
backend/         FastAPI gateway, LangGraph agents, compiler/guard, RCA, search, cache, tests
frontend/        Next.js 15 UI + BFF
docs/PLAN.md     Hackathon plan, decisions, Google access list, schedule
AGENTS.md        Orientation for coding agents and new contributors
```

## Quick start

Requirements: Python 3.12, Node 20+. Docker is optional.

```bash
make setup     # venv + npm install
make data      # 20M synthetic orders into backend/data/panda.duckdb (~3 s)
make api       # gateway on http://localhost:8000
make web       # UI on http://localhost:3000   (in a second terminal)
make test      # backend tests
```

Try these in the UI:
1. "GMV by region for the last 7 days"
2. "Daily conversion rate by channel last 14 days"
3. "Why did GMV drop in the last 14 days?" The synthetic data contains a planted West/Android checkout failure; the RCA should find it (about 99% of the movement)
4. "What is checkout completion rate?"

Speed demo: tick **Force raw table scan** to skip the rollup, **Bypass semantic cache** to skip caching, and compare the query time chips.

## Configuration

Copy `.env.example` to `.env`.

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `mock` (default, offline) or `gemini` |
| `GOOGLE_API_KEY` | AI Studio key for `gemini`; for Vertex AI set `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` |
| `GEMINI_MODEL`, `GEMINI_PRO_MODEL`, `EMBEDDING_MODEL` | Model names (verify availability for your project) |
| `ENGINE` | `duckdb` (BigQuery in phase 2) |
| `DATABASE_URL` | Optional Postgres. When set: pgvector + full-text hybrid search and Postgres LangGraph checkpointer. Run `make up` then `make ingest` |
| `GATEWAY_URL` | Frontend env: gateway address (default `http://localhost:8000`) |

## API

- `POST /api/chat` `{question, thread_id?, force_raw?, bypass_cache?}` returns an SSE stream: `run_started`, `step`*, `result`, `run_finished` (or `error`).
- `GET /api/meta` runtime info, metric list, suggestions, cache stats.
- `POST /api/cache/clear`, `GET /health`.

## Extending the semantic layer

Add a file, no code change needed:
- Metric: `semantic/metrics/<id>.md` with `kind: metric`, `table`, `expr` (or `numerator`/`denominator` for ratios), `dimensions`.
- RCA runbook: `semantic/rca/trees/<id>.md` with `root_metric`, optional `decomposition`, `drill_dimensions`, `hypotheses`.
- Restart the API (catalog is loaded at startup); with Postgres, re-run `make ingest`.

## Status

| Area | State |
|---|---|
| Semantic layer, compiler, guard, cache, RCA, workflow, gateway, UI | done and tested (`make test`) |
| Mock LLM end to end | verified |
| Gemini with real credentials | written, **not yet run** |
| Postgres / pgvector / Postgres checkpointer | written, **not yet run** |
| BigQuery engine, Cloud Run deploy, Google login and roles, Gemma router, benchmark, deck, demo video | phase 2 and 3, see `docs/PLAN.md` |

Known gaps: BigQuery `DATE_TRUNC` transpile needs a fix, gateway has no auth yet (dev only), cache is in-process, local rollup speedup is modest on DuckDB and should be larger on BigQuery.

## License

Apache-2.0 (to be added before submission).
