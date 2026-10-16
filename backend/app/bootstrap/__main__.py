"""One-off provisioning steps, run locally or as Cloud Run Jobs:  python -m app.bootstrap data|index|warm"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import duckdb

from app.bootstrap.bq_load import export_parquet, format_reports, load_tables, user_tables
from app.bootstrap.datagen import generate_dataset
from app.core.config import Settings, get_settings
from app.core.enums import BootstrapStep
from app.core.errors import ConfigurationError, PandaError


def run_data(s: Settings, rows: int, days: int, end: str, from_duckdb: str | None, parquet_dir: str | None, skip_load: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="panda-bootstrap-") as tmp:
        tmp_dir = Path(tmp)
        if from_duckdb:
            db_path = from_duckdb
        else:
            db_path = str(tmp_dir / "panda.duckdb")
            print(f"generating {rows:,} orders ...", flush=True)
            generate_dataset(db_path, s.semantic_dir, rows, days, end)
        con = duckdb.connect(db_path, read_only=True)
        try:
            if skip_load:
                out = Path(parquet_dir or tmp_dir / "parquet")
                for t in user_tables(con):
                    print("wrote", export_parquet(con, t, out))
                return
            if not s.google_cloud_project:
                raise ConfigurationError("GOOGLE_CLOUD_PROJECT is required to load BigQuery")
            from google.cloud import bigquery
            client = bigquery.Client(project=s.google_cloud_project, location=s.bq_location)
            print(format_reports(load_tables(client, con, s.bq_dataset, s.bq_location, tmp_dir / "parquet")))
        finally:
            con.close()


def run_index(s: Settings) -> None:
    from app.search.ingest import build_index
    print(f"indexed {build_index(s)} docs")


def run_warm(s: Settings) -> int:
    """Replays the demo questions through the graph so shared caches are pre-filled. Returns the number of failures."""
    import uuid

    from app.api.controllers.meta import SUGGESTIONS
    from app.container import build_container

    container = build_container(s)
    failures = 0
    try:
        for q in SUGGESTIONS:
            try:
                final = None
                for update in container.runner.stream(q, f"warm-{uuid.uuid4().hex[:8]}", {"force_raw": False, "bypass_cache": False}):
                    final = update.response or final
                print(f"ok    {final['type'] if final else '-':8s} {q}")
            except Exception as e:  # keep warming the rest
                failures += 1
                print(f"FAIL  {q}: {e}")
        print("cache:", container.cache.stats())
    finally:
        container.close()
    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.bootstrap")
    sub = ap.add_subparsers(dest="step", required=True)
    d = sub.add_parser(BootstrapStep.DATA, help="generate synthetic data and load it into BigQuery")
    d.add_argument("--rows", type=int, default=20_000_000)
    d.add_argument("--days", type=int, default=120)
    d.add_argument("--end", default="2026-09-30")
    d.add_argument("--from-duckdb", help="reuse an existing DuckDB file instead of generating")
    d.add_argument("--skip-load", action="store_true", help="only write Parquet files (see --parquet-dir)")
    d.add_argument("--parquet-dir")
    sub.add_parser(BootstrapStep.INDEX, help="build the semantic index in Postgres/AlloyDB")
    sub.add_parser(BootstrapStep.WARM, help="replay demo questions to pre-fill the cache")
    args = ap.parse_args(argv)
    s = get_settings()
    try:
        if args.step == BootstrapStep.DATA:
            run_data(s, args.rows, args.days, args.end, args.from_duckdb, args.parquet_dir, args.skip_load)
        elif args.step == BootstrapStep.INDEX:
            run_index(s)
        else:
            return 1 if run_warm(s) else 0
    except PandaError as e:
        print(f"error: {e.message}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
