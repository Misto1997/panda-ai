PY := backend/.venv/bin
# Active profile = config/profiles/<name>.yaml, e.g.  make api PANDA_PROFILE=prod
export PANDA_PROFILE ?= local
.PHONY: gcp-refresh gcp-hosting probe doctor gcp-diagnose config setup data test bench api api-debug ask web up ingest typecheck gcp-setup gcp-build gcp-deploy gcp-bootstrap gcp-budget gcp-smoke

probe:            ## latency/UX probe of a running instance (needs only `pip3 install httpx`): make probe API=https://panda-api-....run.app WEB=https://panda-web-....run.app ID_TOKEN=eyJ...
	$(or $(wildcard backend/.venv/bin/python),python3) backend/scripts/probe.py --api $(or $(API),http://localhost:8000) $(if $(WEB),--web $(WEB),) $(ARGS)

doctor:           ## check every dependency of the active profile (warehouse, database, index, model); LLM=1 makes one real model call
	cd backend && PYTHONPATH=. ../$(PY)/python -m app.bootstrap diagnose $(if $(LLM),--llm,)

config:           ## show the effective configuration for the active profile (secrets redacted)
	cd backend && PYTHONPATH=. ../$(PY)/python -m app.config_show

setup:            ## install backend + frontend deps
	python3.12 -m venv backend/.venv && $(PY)/pip install -e "backend[dev]"
	npm --prefix frontend install

data:             ## generate synthetic Acme Retail data (20M orders) into DuckDB; ARGS="--rows 2000000" for smaller
	cd backend && PYTHONPATH=. ../$(PY)/python scripts/generate_data.py $(ARGS)

test:
	cd backend && PYTHONPATH=. ../$(PY)/python -m pytest -q

bench:            ## golden question benchmark through the full graph (set LLM_PROVIDER=gemini to grade a real model): make bench ARGS="-v"
	cd backend && PYTHONPATH=. ../$(PY)/python -m app.bench $(ARGS)

api:              ## query gateway on :8000
	cd backend && ../$(PY)/uvicorn app.main:app --reload --port 8000

api-debug:        ## gateway with DEBUG logs, SQL and model payloads in the log
	cd backend && TRACE_PAYLOADS=true LOG_LEVEL=DEBUG ../$(PY)/uvicorn app.main:app --reload --port 8000 --log-level debug

ask:              ## one question in the terminal with a live trace: make ask Q="why did visits drop?" [DEBUG=1]
	cd backend && PYTHONPATH=. ../$(PY)/python -m app.cli "$(Q)" $(if $(DEBUG),--debug,)

web:              ## UI + BFF on :3000
	npm --prefix frontend run dev

typecheck:
	cd frontend && npx tsc --noEmit

up:               ## optional Postgres + pgvector
	docker compose up -d postgres

ingest:           ## index semantic/ into pgvector (needs DATABASE_URL)
	cd backend && PYTHONPATH=. ../$(PY)/python -m app.search.ingest

# --- Google Cloud (read docs/GCP_SETUP.md; needs deploy/env.sh) ---
gcp-setup:        ## APIs, Artifact Registry, secrets, service account roles
	deploy/00-setup.sh

gcp-build:        ## Cloud Build both images
	deploy/10-build.sh

gcp-deploy:       ## deploy API then web to Cloud Run
	deploy/20-deploy-api.sh && deploy/30-deploy-web.sh

gcp-bootstrap:    ## Cloud Run Jobs: load BigQuery, index AlloyDB, warm cache (STEP=data|index|warm|all)
	deploy/40-bootstrap-job.sh $(or $(STEP),all)

gcp-budget:       ## budget alerts + kill-switch
	deploy/50-budget.sh

gcp-smoke:        ## curl the deployed services
	deploy/60-smoke.sh

gcp-diagnose:     ## run the diagnostics inside the VPC as a Cloud Run Job (reads the private database; one real Gemini call)
	deploy/40-bootstrap-job.sh diagnose

gcp-refresh:      ## nightly data roll-forward: make gcp-refresh CMD=create|run|pause|resume|extend|status|delete [DAYS=30]
	deploy/45-nightly-refresh.sh $(or $(CMD),status) $(DAYS)

gcp-hosting:      ## free <site>.web.app address via Firebase Hosting: make gcp-hosting HOSTING_SITE=panda-ai
	deploy/70-hosting.sh
