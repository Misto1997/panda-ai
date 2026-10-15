# AGENTS.md

PANDA (Prompt-driven Analytics & Natural Data Access): natural-language analytics over a governed semantic layer, with root-cause analysis. Built for the Google AI Builder Cup (theme: Future of Work & Enterprise Productivity). Full plan: `docs/PLAN.md`.

## Hard rules

- **Clean-room project.** All code, prompts, data and semantic files must be original and synthetic ("Acme Retail"). Never copy, paste or paraphrase-by-file from any employer or private repo, and never add company names, hostnames, IPs, internal package registries, model names or real data. The hackathon only accepts fresh work.
- Never commit secrets. `.env`, `backend/data/`, `.venv/`, `node_modules/` are gitignored. Use `.env.example` for new config keys.
- The LLM must never write raw SQL. It fills a `QueryIR`; code compiles SQL; the guard validates it.
- Do not commit or push unless the user asks.

## Layout

```
semantic/            Governed layer (markdown + YAML frontmatter): metrics, dimensions, tables, glossary, rca/{trees,checks,policies}
backend/app/
  main.py            FastAPI gateway, SSE /api/chat, /api/meta, /api/cache/clear
  agents.py          LangGraph: route -> plan -> execute -> respond | rca | discover | help
  llm.py, mock_llm.py  LLM + embeddings abstraction; `mock` runs offline and is the test double
  engine.py          Query engines (DuckDB now; BigQuery is phase 2)
  query/             ir.py (QueryIR), timeutil.py, compiler.py, guard.py
  semantic/          catalog.py (loader), search.py (hybrid BM25/FTS + vector, RRF), ingest.py (pgvector)
  rca.py             Deterministic RCA walker (log-ratio decomposition, segment drill, hypothesis tests)
  cache.py, viz.py, fmt.py, config.py
backend/scripts/generate_data.py   Synthetic data with a planted West/Android checkout anomaly
backend/tests/       pytest
frontend/            Next.js 15 UI + BFF (app/api/chat proxies SSE to the gateway)
```

## Setup and commands

Python 3.12, Node 20+. Run from repo root.

```bash
make setup    # venv + npm install
make data     # generate 20M-row DuckDB (backend/data/panda.duckdb); ARGS="--rows 2000000" for smaller
make api      # gateway on :8000
make web      # UI on :3000 (GATEWAY_URL env overrides the gateway, default http://localhost:8000)
make test     # backend pytest
make up       # optional Postgres + pgvector (docker compose)
make ingest   # index semantic/ into pgvector (needs DATABASE_URL)
cd frontend && npx tsc --noEmit   # typecheck UI
```

Backend scripts and tests need `PYTHONPATH=backend` (the Makefile handles it).

## Configuration (`.env`, see `.env.example`)

- `LLM_PROVIDER=mock|gemini`. Mock needs no credentials. Gemini needs `GOOGLE_API_KEY` (AI Studio) or Vertex env vars. Model names are configurable and unverified; check they exist.
- `ENGINE=duckdb`. `DATABASE_URL` empty means in-memory search and checkpointer; set it for pgvector + Postgres checkpointer.

## Key conventions

- **Semantic files** are the source of truth. Add a metric by adding `semantic/metrics/<id>.md` with `kind: metric`, `table`, `expr` or `numerator`/`denominator`, and `dimensions`. Ratio metrics are always computed from sums, never averaged.
- **Rollup selection:** the compiler uses the table's `rollup` if every requested dimension is in `rollup_dimensions`, otherwise `raw`. The raw table has `orders = 1` so metric expressions are identical on both.
- **Time:** relative expressions resolve against the dataset anchor (latest date), half-open `[start, end)`. Dataset ends 2026-09-30.
- **SQL dialect:** compiler emits DuckDB SQL; `engine.transpile` uses sqlglot for other engines.
- **RCA:** the walker computes all numbers; the LLM only narrates the facts JSON. New runbooks go in `semantic/rca/trees/` (`root_metric`, optional `decomposition`, `drill_dimensions`, `hypotheses` with `test: funnel_walk|metric_shift` and numeric `threshold`).
- **Per-turn state:** graph state is checkpointed per thread; `route` resets per-turn fields, only `last_ir` carries over for follow-ups.
- **Events:** SSE stream emits `run_started`, `step`, `result`, `error`, `run_finished`. The UI types live in `frontend/lib/types.ts`; keep them in sync with the gateway payload.

## Testing

- `make test` must pass before finishing a change. Tests run on the mock LLM and the generated DuckDB, so run `make data` first.
- `tests/test_core.py::test_rca_finds_planted_anomaly` guards the demo story; if you change the data generator, keep the West/Android anomaly findable.
- Add tests only for non-trivial logic; extend `tests/test_core.py` rather than creating new files.

## Status and known gaps

Done: semantic layer, compiler, guard, cache, RCA, workflow, SSE gateway, UI (mock LLM verified).
Not yet verified: Gemini calls with real credentials; Postgres/pgvector path (Docker Hub was unreachable in dev).
Phase 2 (not started): BigQuery engine (fix `DATE_TRUNC` transpile on DATE), Cloud Run deploy, Google login/authz, Gemma router, Postgres-backed cache, benchmark, deck, demo video.
Dev auth only: no authentication on the gateway yet.

## Dev environment notes

- `preview_start` configs live in `.claude/launch.json` (gitignored); they use absolute paths because the preview runner has no usable cwd.
- If ports 8000/3000 are busy, stop stale `uvicorn`/`next` processes before starting.
