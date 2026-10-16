# AGENTS.md

PANDA AI (Prompt-driven Analytics & Natural Data Access): natural-language analytics over a governed semantic layer, with guarded text-to-SQL and root-cause analysis (RCA). Deep dives in `docs/`: ARCHITECTURE, CONFIGURATION, GCP_SETUP, DEBUGGING, FRONTEND_GUIDE.

## Hard rules

- **Clean-room, synthetic only.** All code, prompts, data and semantic files are original ("Acme Retail"). Never add company names, internal system names, hostnames, project ids, emails or real data.
- **Never commit secrets.** `.env*`, `deploy/env.sh`, `backend/data/`, `.venv/`, `node_modules/` are gitignored. New config keys go in `.env.example`.
- **Q&A is guarded text-to-SQL.** The LLM writes SQL over *logical* tables only. `LogicalGuard` validates, the rewriter maps logical to physical (rollup or raw), the engine dry-runs, failures feed a bounded repair loop. `QueryIR` is derived from the SQL (cache keys, follow-ups), is the deterministic fallback, and drives RCA.
- **Never let the model invent dates.** Periods come from `extract_time_expr` plus the planner's period guard and data-range guard; plan-cache keys carry the data anchor date.
- Do not commit or push unless asked. Do not delete files without the user's say-so.

## Layout

```
semantic/        OKF knowledge files (markdown + YAML frontmatter, one typed node per file): metrics, dimensions, tables, glossary, examples (question->SQL), rca/{trees,checks,policies}
backend/app/
  main.py            create_app(): controllers, middleware, lifespan
  container.py       Composition root (the only place concrete implementations are chosen)
  core/              config.py (Settings, profiles), enums.py, errors.py, logging.py, db.py (Postgres pool)
  semantic/          models, loader (validates cross-references at startup), catalog
  search/            hybrid (BM25/FTS + vectors, RRF, graph expansion), memory, pgvector, ingest
  llm/               base (ports: structured, text, agent_step), gemini, vertex, mock (offline + test double), embeddings, budget
  prompts/           registry.py (single register of prompts), context.py
  engines/           duckdb (local), bigquery + bigquery_sql
  query/             logical schema, guard, rewriter, normalizer (SQL->IR), service, compiler (IR fallback), period (anchor + TTL re-read)
  cache/             semantic_cache (plan + result layers), memory/postgres stores
  rca/               investigator, decomposition (LMDI), drill (Kitagawa), hypotheses, checks, reader (parallel, memoised)
  agents/            graph, runner, base (AgentNode), routing (rules), judge + tools (LLM judge), nodes/{router,planner,executor,responder,narrate,rca,discovery,help,meta}
  history/           per-user chat history + feedback stores (memory or Postgres)
  security/          Firebase auth, daily quotas, rate limits
  presentation/      a2ui (surface builder + catalog), chart, formatting, narrative (deterministic text), suggestions
  api/               controllers/{chat,meta,admin,health,me,a2ui,history,feedback}, streaming (AG-UI), middleware
  bootstrap/         datagen, bq_load, prune, `python -m app.bootstrap data|index|warm|diagnose|refresh|prune`
deploy/          gcloud scripts, Cloud Build files, budget kill-switch; env.example.sh -> env.sh (gitignored)
frontend/        Next.js 15 UI + BFF: AG-UI client (lib/sse.ts), A2UI renderer (components/a2ui), Firebase auth
config/profiles/ local.yaml, prod.yaml
```

## Commands

Python 3.12, Node 20+. Run from the repo root; the Makefile sets `PYTHONPATH=backend`.

```bash
make setup | data | api | web     # install, 20M-order DuckDB (ARGS="--rows 2000000"), gateway :8000, UI :3000
make test | typecheck             # backend pytest, tsc --noEmit
make ask Q="why did visits drop?" [DEBUG=1]   # one turn in the terminal with a step trace
make bench                        # golden questions through the full graph (LLM_PROVIDER=gemini to grade a real model)
make gcp-bootstrap STEP=accuracy  # same golden benchmark on the deployed stack (real model + BigQuery; dates follow the live data window)
make config | doctor              # effective settings, dependency self-check
make probe API=... WEB=... ID_TOKEN=...       # latency/UX probe of a running deployment (needs pip3 install httpx)
make gcp-setup|build|deploy|bootstrap|refresh|hosting|budget|smoke|diagnose   # see docs/GCP_SETUP.md
```

## Configuration

Profiles in `config/profiles/*.yaml` (`PANDA_PROFILE`, default `local`; `prod` is enforced at startup). Precedence: env > `.env` > profile YAML > code defaults. Component choices are enums (`llm_provider`, `engine`, `search_backend`, `checkpointer`, `cache_store`, `quota_store`, `history_store`, `auth_mode`). Secrets only in env, `.env` or Secret Manager. Details: `docs/CONFIGURATION.md`.

## How a turn flows

`route` (rules, else the LLM judge) -> `plan` (retrieve, Gemini writes SQL, guard, dry-run, repair) -> `execute` -> `respond` -> `narrate` (optional insights after the data is shown); or `rca` -> `narrate`; or `discover`, `help` (static replies + suggestions), `meta` (previous SQL, filters, data range from `last_facts`, no query).

- Q&A uses ONE model call plus optional narration. The stream sends the result twice on purpose (standard summary first, `meta.narrated=true` upgrade later). `NarrateNode` never replaces a good response with an error.
- The judge (`agents/judge.py`, tools in `agents/tools.py`: data_range, resolve_period, search_semantic_layer, last_query, decide) runs only when rules cannot place a message; max 3 model turns; unusable output falls back to the planner; an unavailable model surfaces a "busy" message.
- Model calls are bounded: `llm_timeout_s` 25, `llm_max_retries` 1, `llm_max_concurrency` 6 per instance, narration 12 s no retries, per-turn call cap. Provider error text goes to logs and `details`, never to users.
- The anchor (latest data date) is re-read every 60 s; the nightly refresh job (`deploy/45-nightly-refresh.sh`) rolls the synthetic data forward and stops after its `--until` date.

## Conventions

- **Add a metric:** `semantic/metrics/<id>.md` (`kind: metric`, `table`, `expr` or `numerator`+`denominator`, `dimensions`, `direction`). Ratios are ratios of sums. The loader fails fast on bad references.
- **Add an engine / LLM / search backend:** implement the port in `*/base.py`, register in `factory.py`.
- **Add a graph node:** subclass `AgentNode`, implement `run`, add to `NODE_CLASSES` in `agents/graph.py`, register its prompt in `prompts/registry.py`.
- **Add a hypothesis type:** subclass `HypothesisTester`, register in `TESTERS`. Runbooks (`semantic/rca/trees`) carry thresholds.
- **No bare strings across modules:** use `core/enums.py`. Raise `PandaError` subclasses; `user_facing=True` means the message may be shown.
- **Rollups:** the rewriter uses a table's rollup if every requested dimension is in `rollup_dimensions`, else raw. City is raw-only.
- **Time:** relative expressions resolve from the data anchor, half-open `[start, end)`.
- **Per-turn state:** checkpointed per thread, JSON-serialisable. `RouterNode` resets per-turn fields via `TURN_RESET`; `last_ir`, `last_sql`, `last_facts` carry over for follow-ups.
- **Wire contracts:** the stream is **AG-UI** (`schemas/agui.py`). Answers render through an **A2UI** surface (`presentation/a2ui.py`; catalog `a2ui_catalog.json` is copied to `frontend/components/a2ui/catalog.json`: keep both identical). `schemas/chat.py`, `rca/models.py` and `frontend/lib/types.ts` change together.
- **Dependencies are injected** (`NodeDependencies`); do not import singletons inside nodes.

## Testing

- `make test` and `make typecheck` must pass before finishing a change. Tests use the mock LLM and the generated DuckDB.
- `tests/test_rca_scenarios.py` guards the demo story: the planted anomalies (cancellation spike in Express x South, tracking loss in Mall x East, Grocery mix shift in Wholesale x North) must stay findable. If you change `datagen.py`, keep them findable.
- Add tests for non-trivial logic only; extend the closest existing file.

## Status

Offline (mock LLM, DuckDB): fully tested. Deployed on Google Cloud: Cloud Run (web, api, jobs), AlloyDB, BigQuery, Vertex Gemini, Firebase Auth. Real-model answer quality is not graded by the offline benchmark: run `LLM_PROVIDER=gemini make bench` or `make gcp-bootstrap STEP=accuracy`. Accuracy = execution accuracy: result set equals ground-truth SQL on the physical tables (`backend/app/golden/golden.yaml`). Not load tested. gcloud flags marked unverified in `deploy/` and `docs/GCP_SETUP.md` should be checked against current gcloud docs.

## Dev environment notes

- `.claude/launch.json` (gitignored) holds preview configs. Ports 8000 and 3000 are often taken by the developer's own `make api` / `make web`; check `lsof -nP -iTCP:8000 -sTCP:LISTEN` and reuse them instead of killing them. Do not run `next build` while `make web` is running (it overwrites `frontend/.next`).
