# AGENTS.md

PANDA AI (PANDA = Prompt-driven Analytics & Natural Data Access): natural-language analytics over a governed semantic layer, with guarded text-to-SQL and root-cause analysis (RCA). Built for the Google AI Builder Cup (theme: Future of Work & Enterprise Productivity). Deep dive: `docs/ARCHITECTURE.md`, `docs/FRONTEND_GUIDE.md`, `docs/PHASE2_PLAN.md`, deployment: `docs/GCP_SETUP.md`, debugging: `docs/DEBUGGING.md`, config: `docs/CONFIGURATION.md`.

## Hard rules

- **Clean-room project.** All code, prompts, data and semantic files must be original and synthetic ("Acme Retail"). Never copy or paraphrase files from any employer or private repo, and never add company names, internal system or product names, hostnames, IPs, registries, model names or real data. The hackathon only accepts fresh work. Do not commit planning notes that name internal systems.
- Never commit secrets. `.env`, `backend/data/`, `.venv/`, `node_modules/` are gitignored. New config keys go in `.env.example`.
- **Question answering is guarded text-to-SQL.** The LLM writes SQL over *logical* tables only; `SqlGuard` validates it, a sqlglot rewriter maps logical to physical (rollup or raw) tables, the engine dry-runs it, and failures feed a bounded repair loop. `QueryIR` is derived from the SQL (cache keys, follow-ups), is the deterministic fallback, and drives RCA.
- Do not commit or push unless the user asks. Do not delete files or directories without the user's say-so.

## Layout

```
semantic/                 Governed layer (markdown + YAML frontmatter): metrics, dimensions, tables, glossary, examples (question->SQL few-shots), rca/{trees,checks,policies}
backend/app/
  main.py                 create_app(): controllers, middleware, lifespan
  container.py            Composition root (the only place concrete implementations are chosen)
  cli.py / bench.py       `python -m app.cli "q" [--debug]`; `python -m app.bench` golden benchmark
  core/                   config.py, enums.py, errors.py (PandaError, http_status), logging.py, db.py (shared Postgres pool)
  semantic/               models.py, loader.py, catalog.py
  search/                 hybrid.py (RRF + graph expansion), memory.py, pgvector.py, ingest.py, factory.py
  llm/                    base.py (ports), gemini.py + vertex.py (Agent Platform via ADC), mock.py (offline + test double), embeddings.py, budget.py (per-turn call cap)
  prompts/                registry.py (single register of all prompts), context.py (SQL prompt context)
  engines/                base.py (QueryEngine port), duckdb_engine.py, bigquery_engine.py + bigquery_sql.py, factory.py
  query/                  logical.py (logical schema), guard.py, rewriter.py (logical->physical), render.py, normalizer.py (SQL->IR), service.py, compiler.py (IR fallback + RCA), ir.py, period.py
  cache/                  semantic_cache.py (plan + result layers), store.py (in-memory), postgres_store.py
  rca/                    investigator, decomposition, drill, hypotheses (Strategy), checks (Strategy), reader, models
  agents/                 state, base (AgentNode template), deps, graph, runner, checkpoint, contracts, nodes/{router,planner(SqlPlannerNode),executor,responder,rca,discovery,help}
  security/               auth.py (Firebase ID token), quota.py (per-user/global daily), limits.py (IP rate, body size), service.py
  schemas/                chat.py (ChatResult...), agui.py (AG-UI events)
  presentation/           chart.py, formatting.py, narrative.py, a2ui.py + a2ui_catalog.json
  api/                    controllers/{chat,meta,admin,health,me,a2ui}.py, streaming.py (ChatStreamService), sse.py (AgUiEncoder), middleware.py, errors.py
  bootstrap/              datagen.py, bq_load.py, prune.py, __main__.py (`python -m app.bootstrap data|index|warm|diagnose|refresh|prune`)
deploy/                   gcloud scripts (setup, build, deploy, bootstrap job, budget, kill-switch, smoke); env.example.sh -> env.sh (gitignored)
frontend/                 Next.js 15 UI + BFF: AG-UI client (lib/sse.ts), A2UI renderer (components/a2ui), Firebase auth (components/AuthProvider.tsx)
```

## Commands

Python 3.12, Node 20+. Run from the repo root.

```bash
make setup        # venv + npm install
make data         # 20M-order DuckDB at backend/data/panda.duckdb; ARGS="--rows 2000000" for smaller
make api          # gateway :8000 (reload)     make api-debug   # DEBUG logs + SQL + model payloads
make web          # UI :3000                    make typecheck   # tsc --noEmit
make probe API=... WEB=... ID_TOKEN=...   # latency/UX probe of a running instance (needs `pip3 install httpx`)
make gcp-refresh CMD=create|pause|extend|delete   # nightly data roll-forward with a stop date
make gcp-hosting HOSTING_SITE=panda-ai            # free <site>.web.app address
make doctor | gcp-diagnose   # dependency self-check (local | inside the VPC as a Cloud Run Job)
make test         # backend pytest           make bench   # golden questions through the full graph (LLM_PROVIDER=gemini to grade a real model)
make gcp-setup | gcp-build | gcp-deploy | gcp-bootstrap | gcp-budget | gcp-smoke   # see docs/GCP_SETUP.md (run where gcloud is logged in)
make ask Q="why did visits drop?" [DEBUG=1]    # one turn in the terminal with a step trace
make up / make ingest   # optional Postgres + pgvector, then index semantic/ (needs DATABASE_URL)
```

Backend scripts and tests need `PYTHONPATH=backend`; the Makefile sets it.

## Configuration

Profiles in `config/profiles/*.yaml` (`PANDA_PROFILE`, default `local`; `prod` is enforced at startup by `Settings` validators). Precedence: env > `.env` > profile YAML > code defaults. `make config` prints the effective values. Component choices are explicit enums: `llm_provider`, `engine`, `search_backend`, `checkpointer`, `cache_store`, `quota_store`, `auth_mode`. Details and recipes: `docs/CONFIGURATION.md`. Secrets only in env/`.env`/Secret Manager, never YAML.

### Legacy notes (`.env`, see `.env.example`)

`LLM_PROVIDER=mock|gemini` (mock needs no credentials; gemini needs `GOOGLE_API_KEY` or Vertex env vars; model names are unverified defaults). `ENGINE=duckdb`. `DATABASE_URL` is only used by components whose kind is postgres/pgvector. `LOG_LEVEL`, `TRACE_PAYLOADS`.

## Conventions

- **Add a metric** by adding `semantic/metrics/<id>.md` (`kind: metric`, `table`, `expr` or `numerator`+`denominator`, `dimensions`). Ratios are always ratios of sums. The loader validates every cross-reference at startup and fails fast.
- **Add an engine / LLM / search backend:** implement the port in `*/base.py`, register in the matching `factory.py`.
- **Add a graph node:** subclass `AgentNode`, implement `run`, add to `NODE_CLASSES` in `agents/graph.py`, register its prompt in `prompts/registry.py`.
- **Add a hypothesis type:** subclass `HypothesisTester`, register in `TESTERS`, add to `HypothesisTest`. Runbooks (`semantic/rca/trees`) carry thresholds.
- **No bare strings across modules:** use `core/enums.py`. Raise `PandaError` subclasses; `user_facing=True` means the message may be shown to users.
- **Rollup selection:** the compiler uses a table's `rollup` if every requested dimension is in `rollup_dimensions`, else `raw`. City is raw-only by design.
- **Time:** relative expressions resolve from the dataset anchor (latest date, 2026-09-30), half-open `[start, end)`.
- **Per-turn state:** checkpointed per thread; `RouterNode` resets per-turn fields via `TURN_RESET`; only `last_ir` carries over for follow-ups. State must stay JSON-serialisable.
- **Wire contracts:** the stream is the open **AG-UI** protocol (`schemas/agui.py`: RUN_STARTED, STEP_*, TEXT_MESSAGE_*, ACTIVITY_SNAPSHOT `a2ui-surface`, CUSTOM `panda.step` / `panda.result`, RUN_FINISHED, RUN_ERROR). Answers render through an **A2UI** surface (`presentation/a2ui.py`; catalog in `a2ui_catalog.json`, copied to `frontend/components/a2ui/catalog.json`: keep the two in sync). `schemas/chat.py`, `rca/models.py` and `frontend/lib/types.ts` must change together.
- **Dependencies are injected** (`NodeDependencies`); do not import singletons inside nodes.

## Testing

- `make test` must pass before finishing a change. Tests use the mock LLM and the generated DuckDB.
- `tests/test_rca_scenarios.py` guards the demo story: each planted anomaly (cancellation spike in Express x South, tracking loss in Mall x East, Grocery mix shift in Wholesale x North) must stay findable. If you change `generate_data.py`, keep them findable.
- Add tests for non-trivial logic only; extend the closest existing file.

## Status and known gaps (updated)

Done and tested offline (mock LLM, DuckDB; 147 tests): text-to-SQL path with guard, rewriter, dry-run, repair loop, IR fallback, SQL->IR cache keys; RCA; AG-UI + A2UI UI; auth and quota code; BigQuery SQL translation; golden benchmark harness; Dockerfiles and deploy scripts.
**Unverified (needs real GCP):** Gemini/Agent Platform calls and model ids (`gemini-3.8-flash` default), BigQuery load and queries, AlloyDB/Postgres (pool, pgvector DDL, cache store, quota tables), Firebase sign-in end to end, Direct VPC egress, both Docker builds, every gcloud flag marked unverified in `deploy/` and `docs/GCP_SETUP.md`. The golden benchmark on the mock only validates the harness; real accuracy comes from `LLM_PROVIDER=gemini make bench`.
Target hosting: Cloud Run (web, api, jobs) + AlloyDB (Postgres + pgvector; Cloud SQL works by changing `DATABASE_URL`) + BigQuery + Vertex Gemini (`location=global`) + Firebase Auth only. Nothing runs on a laptop in production.

## Dev environment notes

- `.claude/launch.json` (gitignored) holds preview configs with absolute paths. Ports 8000 and 3000 are often already taken by the user's own `make api` / `make web`; check `lsof -nP -iTCP:8000 -sTCP:LISTEN` and reuse them rather than killing them.

## Latency design (read before changing the turn flow)
- Q&A uses ONE model call (write SQL) plus an optional narration call that runs after the data is already streamed; routing is rule-based (model only if ambiguous); RCA needs no model call before the investigation and runs its warehouse reads concurrently (memoised `SegmentReader`).
- The stream sends the result twice on purpose: first a standard summary with the data, later the same result with `meta.narrated=true` and model text (the UI replaces the first; TEXT_MESSAGE_START resets text). `NarrateNode` must never replace a good response with an error.
- Model calls are bounded: `llm_timeout_s` 25, `llm_max_retries` 1, `llm_max_concurrency` 6 per instance, narration 12 s without retries. Provider error text goes to logs and `details`, never to the user.
- Dates come from the deterministic `extract_time_expr` plus the planner's period guard (SQL must cover the period named in the question); plan-cache keys carry the data anchor date.
- Anchor (data date) is re-read from the warehouse every 60 s (`LazyPeriodResolver` TTL), so a refresh needs no restart. Off-topic and 'who are you' replies are static (`HelpNode`, no model call) with 4 curated clickable `meta.suggestions`; the model router can also return `off_topic`; a model-declined SQL question gets the same style of friendly answer.
- Feedback: `POST /api/feedback` (thumbs, reasons, comment) writes `panda_feedback` (Postgres when `history_store=postgres`); recorded only, nothing reads it back yet.
- Dataset freshness: nightly roll-forward job (`deploy/45-nightly-refresh.sh`, stops after its `--until` date); `prune` removes idle conversation state.
