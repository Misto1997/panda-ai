"""Generate deterministic synthetic Acme Retail data into DuckDB (the logic lives in app.bootstrap.datagen).

Usage: python scripts/generate_data.py [--rows 20000000] [--days 120] [--end 2026-09-30]
"""
import argparse

from app.bootstrap.datagen import generate_dataset
from app.core.config import get_settings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=20_000_000, help="orders to generate")
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--end", default="2026-09-30", help="last date (the dataset anchor)")
    args = ap.parse_args()
    settings = get_settings()
    for table, n in generate_dataset(settings.duckdb_path, settings.semantic_dir, args.rows, args.days, args.end).items():
        print(f"{table:28s}{n:>12,} rows")


if __name__ == "__main__":
    main()
