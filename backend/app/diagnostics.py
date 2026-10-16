"""Self-check of a running configuration: every dependency PANDA AI needs, with a pass/fail and a hint.
Used by GET /api/admin/diagnostics (admins only), `python -m app.bootstrap diagnose` (a Cloud Run Job that can reach the private
database) and `make doctor` locally."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from app.container import Container
from app.core.enums import SearchBackendKind, StoreKind

CHECKPOINT_TABLES = ("checkpoints", "checkpoint_writes", "checkpoint_blobs", "checkpoint_migrations")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    hint: str = ""


class Diagnostics:
    def __init__(self, container: Container) -> None:
        self._c = container

    def run(self, ping_llm: bool = False) -> dict:
        checks: list[Callable[[], CheckResult]] = [self._config, self._warehouse, self._llm_ping if ping_llm else self._llm_info]
        if self._c.pool is not None:
            checks += [self._database, self._extensions, self._tables, self._semantic_index, self._cache_table]
            if self._c.settings.history_store == StoreKind.POSTGRES:
                checks.append(self._history)
            if self._c.settings.checkpointer == StoreKind.POSTGRES:
                checks.append(self._checkpoints)
        results = [self._guard(check) for check in checks]
        return {"ok": all(r.ok for r in results), "checks": [asdict(r) for r in results], "cache": self._c.cache.stats()}

    # ---- helpers ----
    @staticmethod
    def _guard(check: Callable[[], CheckResult]) -> CheckResult:
        try:
            return check()
        except Exception as e:  # a diagnostic must never raise: report the failure instead
            return CheckResult(check.__name__.strip("_"), False, f"{type(e).__name__}: {e}")

    def _query(self, sql: str, params: tuple = ()) -> list:
        with self._c.pool.connection() as conn:
            return conn.execute(sql, params).fetchall()

    # ---- checks ----
    def _config(self) -> CheckResult:
        s = self._c.settings
        detail = (f"profile={s.profile} env={s.app_env.value} llm={s.llm_provider.value} engine={s.engine.value} search={s.search_backend.value} "
                  f"checkpointer={s.checkpointer.value} cache={s.cache_store.value} quota={s.quota_store.value} history={s.history_store.value} auth={s.auth_mode.value}")
        return CheckResult("config", True, detail)

    def _warehouse(self) -> CheckResult:
        svc = self._c.query_service
        tables = {t: self._c.engine.row_count(t) for t in sorted(self._c.catalog.physical_tables())}
        empty = [t for t, n in tables.items() if n == 0]
        return CheckResult("warehouse", not empty, f"anchor={svc.anchor} rows={tables}",
                           "empty or missing tables: run `make gcp-bootstrap STEP=data`" if empty else "")

    def _llm_info(self) -> CheckResult:
        s = self._c.settings
        return CheckResult("llm", True, f"provider={self._c.llm.name} model={s.gemini_model} vertex={s.google_genai_use_vertexai} "
                                        f"location={s.google_cloud_location} (add ?llm=true to make one real call)")

    def _llm_ping(self) -> CheckResult:
        from app.llm.base import Prompt
        text = self._c.llm.text(Prompt("Reply with the single word: pong", "ping"))
        return CheckResult("llm", "pong" in text.lower(), f"{self._c.llm.name} replied: {text.strip()[:60]!r}",
                           "check the model id, the aiplatform.user role and GOOGLE_CLOUD_LOCATION" if "pong" not in text.lower() else "")

    def _database(self) -> CheckResult:
        version = self._query("SELECT version()")[0][0]
        return CheckResult("database", True, version[:80])

    def _extensions(self) -> CheckResult:
        have = {r[0] for r in self._query("SELECT extname FROM pg_extension")}
        ok = "vector" in have
        return CheckResult("extensions", ok, f"installed={sorted(have)}", "" if ok else "run `CREATE EXTENSION vector;` as the admin user")

    def _tables(self) -> CheckResult:
        have = {r[0] for r in self._query("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
        s = self._c.settings
        wanted = []
        if s.search_backend == SearchBackendKind.PGVECTOR:
            wanted.append("semantic_docs")
        if s.checkpointer == StoreKind.POSTGRES:
            wanted += CHECKPOINT_TABLES
        if s.cache_store == StoreKind.POSTGRES:
            wanted.append("panda_cache")
        if s.quota_store == StoreKind.POSTGRES:
            wanted.append("panda_usage")
        if s.history_store == StoreKind.POSTGRES:
            wanted += ["panda_threads", "panda_turns"]
        missing = [t for t in wanted if t not in have]
        return CheckResult("tables", not missing, f"present={sorted(have & set(wanted))} missing={missing}",
                           "semantic_docs is created by `STEP=index`; the others are created on first use" if missing else "")

    def _semantic_index(self) -> CheckResult:
        expected = len(self._c.catalog.docs)
        try:
            count = self._query("SELECT count(*) FROM semantic_docs")[0][0]
            dim = self._query("SELECT vector_dims(embedding) FROM semantic_docs LIMIT 1")
            indexes = [r[0] for r in self._query("SELECT indexname FROM pg_indexes WHERE tablename = 'semantic_docs'")]
        except Exception as e:
            return CheckResult("semantic_index", False, f"cannot read semantic_docs: {e}", "run `make gcp-bootstrap STEP=index`")
        ok = count == expected and bool(dim) and dim[0][0] == self._c.settings.embedding_dim
        return CheckResult("semantic_index", ok, f"docs={count}/{expected} embedding_dim={dim[0][0] if dim else None} indexes={indexes}",
                           "" if ok else "re-run `make gcp-bootstrap STEP=index` (also needed after editing semantic/ files)")

    def _cache_table(self) -> CheckResult:
        if self._c.settings.cache_store != StoreKind.POSTGRES:
            return CheckResult("cache", True, "in-memory store")
        try:
            rows = self._query("SELECT layer, count(*) FROM panda_cache GROUP BY layer")
        except Exception as e:
            return CheckResult("cache", True, f"panda_cache not created yet ({type(e).__name__})")
        return CheckResult("cache", True, f"entries={dict(rows)}")

    def _history(self) -> CheckResult:
        try:
            threads = self._query("SELECT count(*) FROM panda_threads")[0][0]
            turns = self._query("SELECT count(*) FROM panda_turns")[0][0]
        except Exception as e:
            return CheckResult("history", True, f"history tables not created yet ({type(e).__name__})")
        return CheckResult("history", True, f"threads={threads} turns={turns}")

    def _checkpoints(self) -> CheckResult:
        """Conversation-state footprint: how big the LangGraph tables are and how many threads they hold."""
        sizes = dict(self._query("SELECT relname, pg_total_relation_size(relid) FROM pg_catalog.pg_statio_user_tables "
                                 "WHERE relname = ANY(%s)", (list(CHECKPOINT_TABLES),)))
        try:
            threads, rows = self._query("SELECT count(DISTINCT thread_id), count(*) FROM checkpoints")[0]
        except Exception:
            return CheckResult("checkpoints", True, "tables not created yet")
        total_kb = sum(sizes.values()) // 1024
        return CheckResult("checkpoints", total_kb < 200_000, f"threads={threads} checkpoints={rows} size={total_kb} KB ({', '.join(f'{k}={v // 1024}KB' for k, v in sorted(sizes.items()))})",
                           "prune old threads (see docs/DEMO_FIX_PLAN.md)" if total_kb >= 200_000 else "")
