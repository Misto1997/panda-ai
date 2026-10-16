# Build context is the REPO ROOT (needs semantic/):  docker build -f backend/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Layout mirrors the repo so Settings.ROOT (three levels above app/core/config.py) resolves to /srv and semantic/ to /srv/semantic.
WORKDIR /srv/backend

# Dependencies first (cached layer): read them from pyproject.toml, do not install the project itself.
COPY backend/pyproject.toml backend/constraints.txt ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/requirements.txt \
 && pip install -c constraints.txt -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY backend/app ./app
COPY semantic /srv/semantic
COPY config /srv/config

RUN useradd --system --uid 10001 --no-create-home panda
USER panda

ENV PORT=8080 PYTHONPATH=/srv/backend
# Single worker: Cloud Run scales by instances. --proxy-headers so X-Forwarded-For identifies clients; 10 s grace matches Cloud Run's SIGTERM window; keep-alive 620 s exceeds Cloud Run's 10 min idle reuse.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 10 --timeout-keep-alive 620
