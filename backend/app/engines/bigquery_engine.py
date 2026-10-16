"""BigQuery engine. Keyless (Application Default Credentials / Cloud Run service account), location-pinned,
byte-capped, labelled. Receives DuckDB-style SQL from the compiler and translates it (see bigquery_sql)."""
from __future__ import annotations

import concurrent.futures
import time
from datetime import date

from app.core.config import Settings
from app.core.errors import ConfigurationError, EngineError, QueryTimeoutError, QueryTooExpensiveError
from app.core.logging import get_logger
from app.engines.base import DryRunInfo, QueryResult
from app.engines.bigquery_sql import to_bigquery
from app.engines.duckdb_engine import to_jsonable

log = get_logger("engine.bigquery")
JOB_LABELS = {"app": "panda-ai"}
_BYTES_CAP_MARKERS = ("bytes billed", "maximumBytesBilled", "maximum_bytes_billed")


class BigQueryEngine:
    name = "bigquery"
    dialect = "bigquery"
    input_dialect = "duckdb"  # dialect of the SQL handed to run()/dry_run()

    def __init__(self, client, project: str, dataset: str, location: str, max_bytes_billed: int) -> None:
        self._client, self._project, self._dataset = client, project, dataset
        self._location, self._max_bytes = location, max_bytes_billed

    @classmethod
    def from_settings(cls, s: Settings) -> "BigQueryEngine":
        from google.auth.exceptions import DefaultCredentialsError
        from google.cloud import bigquery

        try:
            client = bigquery.Client(project=s.google_cloud_project or None, location=s.bq_location)
        except DefaultCredentialsError as e:
            raise ConfigurationError("BigQuery needs Application Default Credentials (gcloud auth application-default login, "
                                     "or a Cloud Run service account)") from e
        return cls(client, client.project, s.bq_dataset, s.bq_location, s.bq_max_bytes_billed)

    # ---- QueryEngine port ----
    def run(self, sql: str, timeout_s: float) -> QueryResult:
        from google.api_core import exceptions as gexc
        from google.cloud import bigquery

        bq_sql = to_bigquery(sql, self._project, self._dataset)
        config = bigquery.QueryJobConfig(maximum_bytes_billed=self._max_bytes, labels=JOB_LABELS, use_query_cache=True)
        config.job_timeout_ms = int(timeout_s * 1000)
        started = time.perf_counter()
        job = None
        try:
            job = self._client.query(bq_sql, job_config=config, location=self._location)
            rows = list(job.result(timeout=timeout_s))
        except (concurrent.futures.TimeoutError, TimeoutError) as e:
            if job is not None:
                job.cancel()
            raise QueryTimeoutError(f"The query took longer than {timeout_s:.0f}s. Narrow the period or the dimensions.") from e
        except gexc.GoogleAPICallError as e:
            if any(m in str(e) for m in _BYTES_CAP_MARKERS):
                raise QueryTooExpensiveError("That query would scan too much data. Narrow the period or the dimensions.") from e
            raise EngineError(f"BigQuery rejected the query: {e}") from e
        columns = [f.name for f in job.schema]
        out = [[to_jsonable(v) for v in row.values()] for row in rows]
        stats = {"bytes_processed": job.total_bytes_processed or 0, "cache_hit": bool(job.cache_hit)}
        elapsed = (time.perf_counter() - started) * 1000
        log.debug("bigquery: %.1f ms, %d rows, %s bytes, cache_hit=%s", elapsed, len(out), stats["bytes_processed"], stats["cache_hit"])
        return QueryResult(columns, out, elapsed, stats)

    def dry_run(self, sql: str) -> DryRunInfo:
        """Validate without running (free) and report the estimated bytes processed. Matches SupportsDryRun."""
        from google.api_core import exceptions as gexc
        from google.cloud import bigquery

        config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, labels=JOB_LABELS)
        try:
            job = self._client.query(to_bigquery(sql, self._project, self._dataset), job_config=config, location=self._location)
        except gexc.BadRequest as e:  # invalid SQL: surfaced to the repair prompt
            return DryRunInfo(ok=False, error=str(e).splitlines()[0])
        except gexc.GoogleAPICallError as e:
            raise EngineError(f"BigQuery dry run failed: {e}") from e
        return DryRunInfo(ok=True, bytes_processed=int(job.total_bytes_processed or 0))

    def max_date(self, table: str, column: str) -> date:
        value = self._scalar(f"SELECT MAX({column}) FROM {table}")
        if value is None:
            raise EngineError(f"table {table} is empty")
        return value

    def row_count(self, table: str) -> int:
        return int(self._scalar(f"SELECT COUNT(*) FROM {table}"))

    def close(self) -> None:
        self._client.close()

    def _scalar(self, sql: str):
        """First cell as a native Python value (run() would stringify dates)."""
        from google.api_core import exceptions as gexc
        from google.cloud import bigquery

        config = bigquery.QueryJobConfig(maximum_bytes_billed=self._max_bytes, labels=JOB_LABELS)
        try:
            rows = list(self._client.query(to_bigquery(sql, self._project, self._dataset), job_config=config,
                                           location=self._location).result(timeout=30))
        except (gexc.GoogleAPICallError, concurrent.futures.TimeoutError) as e:
            raise EngineError(f"BigQuery metadata query failed: {e}") from e
        return rows[0][0]
