# AGENTS.md

PANDA (Prompt-driven Analytics & Natural Data Access): natural-language analytics over a governed semantic layer, with root-cause analysis (RCA). Built for the Google AI Builder Cup (theme: Future of Work & Enterprise Productivity). Deep dive: `docs/ARCHITECTURE.md`, `docs/FRONTEND_GUIDE.md`.

## Hard rules

- **Clean-room project.** All code, prompts, data and semantic files must be original and synthetic ("Acme Retail"). Never copy or paraphrase files from any employer or private repo, and never add company names, internal system or product names, hostnames, IPs, registries, model names or real data. The hackathon only accepts fresh work. Do not commit planning notes that name internal systems.
- Never commit secrets. `.env`, `backend/data/`, `.venv/`, `node_modules/` are gitignored. New config keys go in `.env.example`.
- **The LLM never writes SQL.** It fills a `QueryIR`; `QueryCompiler` emits SQL; `SqlGuard` validates it.
- Do not commit or push unless the user asks. Do not delete files or directories without the user's say-so.

## Layout

```
semantic/                 Governed layer (markdown + YAML frontmatter): metrics, dimensions, tables, glossary, rca/{trees,checks,policies}
backend/app/
  main.py                 create_app(): wires controllers, middleware, lifespan
  container.py            Composition root (the only place concrete implementations are chosen)
  cli.py                  `python -m app.cli "question" [--debug]`: one turn with a live trace
  core/                   config.py, enums.py (all cross-module strings), errors.py (PandaError taxonomy), logging.py
  semantic/               models.py (pydantic specs), loader.py, catalog.py (validated, cross-referenced)
  search/                 hybrid.py (RRF + graph expansion), memory.py (BM25 + cosine), pgvector.py, ingest.py, factory.py
  llm/                    base.py (ports), gemini.py, mock.py (offline + test double), embeddings.py, factory.py
  prompts/registry.py     The single register of every prompt, each owned by a node
  engines/                base.py (QueryEngine port), duckdb_engine.py, factory.py (registry)
  query/                  ir.py, period.py, compiler.py, guard.py, service.py (compile -> guard -> cache -> run)
  cache/semantic_cache.py Two-layer cache (plan, result), TTL + LRU, thread-safe
  rca/                    investigator.py, decomposition.py, drill.py, hypotheses.py (Strategy), checks.py (Strategy), reader.py, models.py
  agents/                 state.py, base.py (AgentNode template), deps.py, graph.py, runner.py, checkpoint.py, contracts.py, nodes/*
  schemas/chat.py         Wire contracts (ChatRequest, ChatResult, StepEvent ...)
  presentation/           chart.py, formatting.py, narrative.py (deterministic fallbacks)
  api/                    controllers/{chat,meta,admin,health}.py, streaming.py (ChatStreamService), sse.py, middleware.py, errors.py
backend/scripts/generate_data.py   Synthetic data with three planted anomalies
backend/tests/            pytest (needs `make data` first)
frontend/                 Next.js 15 UI + BFF; see docs/FRONTEND_GUIDE.md
```

## Commands

Python 3.12, Node 20+. Run from the repo root.

```bash
make setup        # venv + npm install
make data         # 20M-order DuckDB at backend/data/panda.duckdb; ARGS="--rows 2000000" for smaller
make api          # gateway :8000 (reload)     make api-debug   # DEBUG logs + SQL + model payloads
make web          # UI :3000                    make typecheck   # tsc --noEmit
make test         # backend pytest
make ask Q="why did visits drop?" [DEBUG=1]    # one turn in the terminal with a step trace
make up / make ingest   # optional Postgres + pgvector, then index semantic/ (needs DATABASE_URL)
```

Backend scripts and tests need `PYTHONPATH=backend`; the Makefile sets it.

## Configuration (`.env`, see `.env.example`)

`LLM_PROVIDER=mock|gemini` (mock needs no credentials; gemini needs `GOOGLE_API_KEY` or Vertex env vars; model names are unverified defaults). `ENGINE=duckdb`. `DATABASE_URL` empty = in-memory search, checkpointer and cache; set it for pgvector and the Postgres checkpointer. `LOG_LEVEL`, `TRACE_PAYLOADS`.

## Conventions

- **Add a metric** by adding `semantic/metrics/<id>.md` (`kind: metric`, `table`, `expr` or `numerator`+`denominator`, `dimensions`). Ratios are always ratios of sums. The loader validates every cross-reference at startup and fails fast.
- **Add an engine / LLM / search backend:** implement the port in `*/base.py`, register in the matching `factory.py`.
- **Add a graph node:** subclass `AgentNode`, implement `run`, add to `NODE_CLASSES` in `agents/graph.py`, register its prompt in `prompts/registry.py`.
- **Add a hypothesis type:** subclass `HypothesisTester`, register in `TESTERS`, add to `HypothesisTest`. Runbooks (`semantic/rca/trees`) carry thresholds.
- **No bare strings across modules:** use `core/enums.py`. Raise `PandaError` subclasses; `user_facing=True` means the message may be shown to users.
- **Rollup selection:** the compiler uses a table's `rollup` if every requested dimension is in `rollup_dimensions`, else `raw`. City is raw-only by design.
- **Time:** relative expressions resolve from the dataset anchor (latest date, 2026-09-30), half-open `[start, end)`.
- **Per-turn state:** checkpointed per thread; `RouterNode` resets per-turn fields via `TURN_RESET`; only `last_ir` carries over for follow-ups. State must stay JSON-serialisable.
- **Wire contracts:** `schemas/chat.py` and `rca/models.py` are mirrored by `frontend/lib/types.ts`; update both together.
- **Dependencies are injected** (`NodeDependencies`); do not import singletons inside nodes.

## Testing

- `make test` must pass before finishing a change. Tests use the mock LLM and the generated DuckDB.
- `tests/test_rca_scenarios.py` guards the demo story: each planted anomaly (cancellation spike in Express x South, tracking loss in Mall x East, Grocery mix shift in Wholesale x North) must stay findable. If you change `generate_data.py`, keep them findable.
- Add tests for non-trivial logic only; extend the closest existing file.

## Status and known gaps

Done: semantic layer (13 metrics, 7 dimensions with a 4-level geography, 4 runbooks with 4-5 hypotheses each), compiler, guard, two-layer cache, RCA, workflow, SSE gateway, UI. Verified with the mock LLM only.
Not yet verified: Gemini with real credentials; Postgres/pgvector path (Docker Hub was unreachable in dev); load behaviour.
Phase 2 (not started): BigQuery engine (note `DATE_TRUNC` on DATE needs care when transpiling), Cloud Run deploy, Google login and row-level scope, Gemma router, Postgres-backed cache, benchmark, deck, demo video.
No authentication on the gateway yet.

## Dev environment notes

- `.claude/launch.json` (gitignored) holds preview configs with absolute paths. Ports 8000 and 3000 are often already taken by the user's own `make api` / `make web`; check `lsof -nP -iTCP:8000 -sTCP:LISTEN` and reuse them rather than killing them.
