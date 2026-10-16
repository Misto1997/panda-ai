# Configuration

One codebase, profiles in `config/profiles/*.yaml`. The active profile is `PANDA_PROFILE` (default `local`; `PANDA_PROFILE_FILE` points at an arbitrary file). Every key is a field of `Settings` (`backend/app/core/config.py`) and can be set by an environment variable of the same name (`ENGINE=bigquery`).

```
precedence (highest first):  environment  >  .env  >  config/profiles/<profile>.yaml  >  code defaults
```

Secrets (`DATABASE_URL`, `PGPASSWORD`, `GOOGLE_API_KEY`, `LANGSMITH_API_KEY`) live only in the environment, `.env` or Secret Manager, never in YAML. New keys also go in `.env.example`. `make config` prints the effective values (secrets redacted); `PANDA_PROFILE=prod make config` checks prod.

## Local quick start

Prerequisites: Python 3.12, Node 20+, `make`. No cloud account or API key is needed for the offline mode.

```bash
make setup                   # virtualenv + npm install
make data ARGS="--rows 2000000"   # synthetic DuckDB dataset (default is 20M orders; smaller is faster)
make api                     # backend on :8000 (mock LLM, in-memory state, no login)
make web                     # UI on :3000 (separate terminal)
make test                    # backend tests (mock LLM, generated DuckDB)
```

Offline mode uses `LLM_PROVIDER=mock`, which answers the built-in question set deterministically. For a real model, copy `.env.example` to `.env` and set either `LLM_PROVIDER=gemini` with `GOOGLE_API_KEY`, or Vertex (see Recipes). `make ask Q="why did visits drop?"` runs one turn in the terminal.

## Profiles

| Knob | Values | `local` | `prod` |
|---|---|---|---|
| `app_env` | `local`, `prod` | local | prod |
| `llm_provider` | `mock`, `gemini` | mock | gemini |
| `google_genai_use_vertexai` | bool | false | true (keyless, ADC) |
| `engine` | `duckdb`, `bigquery` | duckdb | bigquery |
| `search_backend` | `memory`, `pgvector` | memory | pgvector |
| `checkpointer`, `cache_store`, `quota_store`, `history_store` | `memory`, `postgres` | memory | postgres |
| `auth_mode` | `dev`, `firebase` | dev (no login) | firebase |
| `text_to_sql` | bool | true | true |
| `cache_enabled` | bool | true | true |
| `trace_payloads` | bool | false | must be false |

**`app_env: prod` is enforced at startup**: the API refuses to boot unless Gemini via Vertex, BigQuery, pgvector, Postgres for all four stores, Firebase auth, cache on and payload tracing off are all selected. Any profile also fails fast on inconsistent settings (a postgres/pgvector component without `DATABASE_URL`; `engine=bigquery` or Vertex without `google_cloud_project`; `auth_mode=firebase` without `firebase_project_id`). A missing non-local profile file is an error.

## Key groups

| Group | Keys (defaults) |
|---|---|
| Model | `gemini_model`, `gemini_pro_model` (`gemini-3.8-flash`; verify the id in your project's model garden), `gemini_thinking_level` (low), `google_cloud_project`, `google_cloud_location` (global), `llm_timeout_s` (25), `llm_max_retries` (1), `llm_max_concurrency` (6), `llm_max_calls_per_turn` (8), `narrate_enabled` (true), `narration_timeout_s` (12), `enforce_time_guard` (true) |
| Embeddings | `embedding_provider` (`auto`, or `hash` for offline / no quota), `embedding_model` (`gemini-embedding-2`), `embedding_location` (empty = model location), `embedding_dim` (768). Rebuild the index after changing any of these |
| Engine | `duckdb_path`, `bq_dataset` (panda), `bq_location` (asia-southeast1), `bq_max_bytes_billed` (10 GiB), `max_rows` (500), `query_timeout_s` (20) |
| Text-to-SQL | `text_to_sql`, `sql_max_repairs` (2), `sql_max_joins` (3), `sql_max_chars` (6000), `sql_max_bytes_processed` (0 = off) |
| Postgres | `database_url`, `db_pool_max` (5), `db_connect_timeout_s` (5), `db_pool_timeout_s` (10), `vector_index` (`none`, `hnsw`, `scann` on AlloyDB) |
| Semantic and cache | `semantic_dir`, `cache_ttl_s` (600; prod 86400), `cache_max_entries` (512, in-memory only) |
| API | `cors_origins`, `max_question_chars` (1000), `sse_heartbeat_s` (15) |
| Auth and limits | `firebase_project_id`, `admin_emails` (comma-separated), `daily_user_query_limit` (30), `daily_global_query_limit` (300), `max_request_bytes` (16384), `ip_rate_per_minute` (300), `ip_rate_burst` (60) |
| Observability | `log_level`, `trace_payloads`; optional `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` for LangGraph tracing |

The deploy scripts set the production environment from `deploy/env.sh` via `deploy/api_env.sh` (profile `prod`, project, models, BigQuery, `DATABASE_URL`, Firebase project, limits, `ADMIN_EMAILS`, embedding settings). `PGPASSWORD` comes from Secret Manager. Edit `config/profiles/prod.yaml` for non-secret production values; add a profile by copying a file and setting `PANDA_PROFILE=<name>`.

## Commands

```bash
make config      # effective configuration
make api         # backend on :8000 with the active profile
make web         # UI on :3000 (GATEWAY_URL defaults to http://localhost:8000)
```

## Recipes

Start from the default local profile; use `.env` or inline variables.

| Goal | Do |
|---|---|
| Fully local and offline | `make data && make api`, then `make web` |
| Real Gemini with an AI Studio key | `.env`: `LLM_PROVIDER=gemini`, `GOOGLE_API_KEY=...` |
| Real Gemini on Vertex | `gcloud auth application-default login`, then `LLM_PROVIDER=gemini GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID` |
| BigQuery engine | ADC as above, `ENGINE=bigquery GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID`; the dataset must be loaded (`python -m app.bootstrap data` or the Cloud Run job) |
| Postgres search, state, cache, history locally | `make up` (or any Postgres with the `vector` extension), `DATABASE_URL=postgresql://panda:panda@localhost:5433/panda`, `SEARCH_BACKEND=pgvector CHECKPOINTER=postgres CACHE_STORE=postgres QUOTA_STORE=postgres HISTORY_STORE=postgres`, then `make ingest` |
| AlloyDB from a laptop | the instance has a private IP: connect through the AlloyDB Auth Proxy to localhost and use the Postgres recipe (not verified here) |
| Sign-in locally | the four `NEXT_PUBLIC_FIREBASE_*` values in `frontend/.env.local`, plus `AUTH_MODE=firebase FIREBASE_PROJECT_ID=YOUR_PROJECT_ID` |
| No embedding quota | `EMBEDDING_PROVIDER=hash`, re-run the index step |
| Debug a turn | `make ask Q="..." DEBUG=1` or `make api-debug` |

Components are independent: real Gemini with DuckDB and in-memory state is a valid, cheap local setup.
