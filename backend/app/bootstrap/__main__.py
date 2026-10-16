"""One-off provisioning steps, run locally or as Cloud Run Jobs:  python -m app.bootstrap data|index|warm"""
from __future__ import annotations

import argparse
import os
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
            generate_dataset(db_path, s.semantic_dir, rows, days, end, memory_limit="6GB", threads=4)
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


def run_refresh(s: Settings, rows: int, days: int, until: str | None) -> int:
    """Nightly roll-forward: regenerate the synthetic dataset so it ends YESTERDAY (UTC), reload BigQuery, clear the cache.
    Does nothing after `until` (an ISO date), so a forgotten scheduler cannot run forever."""
    from datetime import date, datetime, timedelta, timezone

    today = datetime.now(timezone.utc).date()
    if until and today > date.fromisoformat(until):
        print(f"refresh window ended on {until}: nothing to do (pause or delete the Cloud Scheduler job)")
        return 0
    end = (today - timedelta(days=1)).isoformat()
    print(f"rolling the dataset forward to end on {end}", flush=True)
    run_data(s, rows, days, end, None, None, False)
    try:
        from app.cache.semantic_cache import create_cache_store
        store = create_cache_store(s)
        store.clear()  # cached plans/results describe the old date window
        store.close()
        print("cache cleared")
    except Exception as e:  # a cache problem must not fail the data refresh
        print(f"warning: cache not cleared: {e}", file=sys.stderr)
    try:
        from app.bootstrap.prune import prune
        print("pruned old conversation state:", prune(s))
    except Exception as e:  # housekeeping is best effort
        print(f"warning: prune skipped: {e}", file=sys.stderr)
    return 0


def run_diagnose(s: Settings, ping_llm: bool) -> int:
    """Prints every dependency check. Exit code 1 if any fails. Runs inside the VPC when executed as a Cloud Run Job."""
    from app.container import build_container
    from app.diagnostics import Diagnostics

    container = build_container(s)
    try:
        report = Diagnostics(container).run(ping_llm=ping_llm)
    finally:
        container.close()
    for check in report["checks"]:
        print(f"{'PASS' if check['ok'] else 'FAIL'}  {check['name']:15s} {check['detail']}")
        if check["hint"] and not check["ok"]:
            print(f"      hint: {check['hint']}")
    print("cache:", report["cache"])
    return 0 if report["ok"] else 1


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
    rf = sub.add_parser(BootstrapStep.REFRESH, help="roll the dataset forward to end yesterday, reload BigQuery, clear the cache")
    rf.add_argument("--rows", type=int, default=20_000_000)
    rf.add_argument("--days", type=int, default=120)
    rf.add_argument("--until", default=os.environ.get("REFRESH_UNTIL"), help="ISO date after which the job does nothing")
    pr = sub.add_parser(BootstrapStep.PRUNE, help="delete conversation state idle for more than --days and expired cache rows")
    pr.add_argument("--days", type=int, default=7)
    dg = sub.add_parser(BootstrapStep.DIAGNOSE, help="check config, warehouse, database, index (add --llm for one real model call)")
    dg.add_argument("--llm", action="store_true")
    args = ap.parse_args(argv)
    s = get_settings()
    try:
        if args.step == BootstrapStep.DATA:
            run_data(s, args.rows, args.days, args.end, args.from_duckdb, args.parquet_dir, args.skip_load)
        elif args.step == BootstrapStep.INDEX:
            run_index(s)
        elif args.step == BootstrapStep.PRUNE:
            from app.bootstrap.prune import prune
            print(prune(s, args.days))
        elif args.step == BootstrapStep.REFRESH:
            return run_refresh(s, args.rows, args.days, args.until)
        elif args.step == BootstrapStep.DIAGNOSE:
            return run_diagnose(s, args.llm)
        else:
            return 1 if run_warm(s) else 0
    except PandaError as e:
        print(f"error: {e.message}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
