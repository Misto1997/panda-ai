PY := backend/.venv/bin/python
.PHONY: setup data test api web up ingest

setup:            ## install backend + frontend deps
	python3.12 -m venv backend/.venv && backend/.venv/bin/pip install -e "backend[dev]"
	npm --prefix frontend install

data:             ## generate synthetic Acme Retail data (20M raw rows) into DuckDB
	cd backend && PYTHONPATH=. ../$(PY) scripts/generate_data.py $(ARGS)

test:
	cd backend && PYTHONPATH=. ../$(PY) -m pytest -q

api:              ## query gateway on :8000
	cd backend && ../backend/.venv/bin/uvicorn app.main:app --reload --port 8000

web:              ## UI + BFF on :3000
	npm --prefix frontend run dev

up:               ## optional Postgres + pgvector
	docker compose up -d postgres

ingest:           ## index semantic/ into pgvector (needs DATABASE_URL)
	cd backend && PYTHONPATH=. ../$(PY) -m app.semantic.ingest
