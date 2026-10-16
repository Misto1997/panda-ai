"""DuckDB tables -> Parquet -> BigQuery load jobs (no GCS bucket needed). Idempotent: WRITE_TRUNCATE."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from app.core.errors import EngineError
from app.core.logging import get_logger

log = get_logger("bootstrap.bq")


@dataclass(frozen=True)
class TableLayout:
    partition_field: str | None = None
    cluster_fields: tuple[str, ...] = field(default_factory=tuple)


# Partition by day on the date column (120 daily partitions, far below the 10,000 limit); cluster by the most filtered dimensions.
LAYOUTS: dict[str, TableLayout] = {
    "fact_sales": TableLayout("order_date", ("marketplace", "zone")),
    "agg_sales_daily": TableLayout("order_date", ("marketplace", "zone")),
    "agg_traffic_city_daily": TableLayout("visit_date", ("marketplace", "zone")),
    "agg_traffic_state_daily": TableLayout("visit_date", ("marketplace", "zone")),
    "agg_bu_traffic_daily": TableLayout("visit_date", ("marketplace", "business_unit")),
}


@dataclass
class LoadReport:
    table: str
    rows: int
    parquet_bytes: int
    bq_rows: int | None = None
    bq_bytes: int | None = None


def export_parquet(con: duckdb.DuckDBPyConnection, table: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{table}.parquet"
    path.unlink(missing_ok=True)
    # DuckDB SUM(integer) is HUGEINT, which Parquet stores as double (BigQuery FLOAT64): cast to BIGINT to keep exact integers
    cols = [f"CAST({c} AS BIGINT) AS {c}" if t.upper() == "HUGEINT" else c
            for c, t in con.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position").fetchall()]
    con.execute(f"COPY (SELECT {', '.join(cols)} FROM {table}) TO '{path}' (FORMAT PARQUET, COMPRESSION SNAPPY)")
    return path


def user_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    return [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY 1").fetchall()]


def load_config(layout: TableLayout):
    from google.cloud import bigquery

    cfg = bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.PARQUET, write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
    if layout.partition_field:
        cfg.time_partitioning = bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY, field=layout.partition_field)
    if layout.cluster_fields:
        cfg.clustering_fields = list(layout.cluster_fields)
    return cfg


def ensure_dataset(client, dataset: str, location: str) -> None:
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery

    ref = f"{client.project}.{dataset}"
    try:
        client.get_dataset(ref)
    except NotFound:
        ds = bigquery.Dataset(ref)
        ds.location = location
        client.create_dataset(ds)
        log.info("created dataset %s in %s", ref, location)


def load_tables(client, con: duckdb.DuckDBPyConnection, dataset: str, location: str, work_dir: Path) -> list[LoadReport]:
    """One table at a time: export, load, delete the Parquet file (Cloud Run's disk is memory-backed)."""
    from google.api_core.exceptions import GoogleAPICallError

    ensure_dataset(client, dataset, location)
    reports = []
    for table in user_tables(con):
        rows = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        path = export_parquet(con, table, work_dir)
        report = LoadReport(table, rows, path.stat().st_size)
        try:
            with path.open("rb") as fh:
                job = client.load_table_from_file(fh, f"{client.project}.{dataset}.{table}", job_config=load_config(LAYOUTS.get(table, TableLayout())),
                                                  location=location)
                job.result()
            loaded = client.get_table(f"{client.project}.{dataset}.{table}")
        except GoogleAPICallError as e:
            raise EngineError(f"BigQuery load of {table} failed: {e}") from e
        finally:
            path.unlink(missing_ok=True)
        report.bq_rows, report.bq_bytes = loaded.num_rows, loaded.num_bytes
        if report.bq_rows != rows:
            raise EngineError(f"{table}: loaded {report.bq_rows} rows but exported {rows}")
        reports.append(report)
    return reports


def format_reports(reports: list[LoadReport]) -> str:
    lines = [f"{r.table:28s}{r.rows:>14,} rows  parquet {r.parquet_bytes / 1e6:>8.1f} MB  bigquery {((r.bq_bytes or 0) / 1e6):>8.1f} MB" for r in reports]
    total = sum(r.bq_bytes or r.parquet_bytes for r in reports)
    lines.append(f"{'TOTAL':28s}{sum(r.rows for r in reports):>14,} rows  stored ~{total / 1e9:.2f} GB (active storage ~USD {total / 1e9 * 0.02:.3f}/month at list price, unverified)")
    return "\n".join(lines)
