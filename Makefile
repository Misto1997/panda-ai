PY := backend/.venv/bin
.PHONY: setup data test api api-debug ask web up ingest typecheck

setup:            ## install backend + frontend deps
	python3.12 -m venv backend/.venv && $(PY)/pip install -e "backend[dev]"
	npm --prefix frontend install

data:             ## generate synthetic Acme Retail data (20M orders) into DuckDB; ARGS="--rows 2000000" for smaller
	cd backend && PYTHONPATH=. ../$(PY)/python scripts/generate_data.py $(ARGS)

test:
	cd backend && PYTHONPATH=. ../$(PY)/python -m pytest -q

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
