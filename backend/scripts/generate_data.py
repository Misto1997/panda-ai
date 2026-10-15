"""Generate deterministic synthetic Acme Retail data into DuckDB.

Geography comes from semantic/dimensions/city.md so the data and the semantic layer cannot drift.

Three anomalies are planted in the last ANOMALY_DAYS days, each in a different segment and visible to a
different RCA runbook (see tests/test_rca_scenarios.py):
  A. Cancellation spike  : Acme Express x South zone, cancellation probability 6% -> 60%    (Net GMV falls)
  B. Visit tracking loss : Acme Mall x East zone, visits x0.45, orders unchanged            (Visits fall, conversion rises)
  C. Business-unit mix   : Acme Wholesale x North zone, 45% of orders re-assigned to Grocery (ASP falls)

Usage: python scripts/generate_data.py [--rows 20000000] [--days 120] [--end 2026-09-30]
"""
import argparse
from pathlib import Path

import duckdb

from app.core.config import get_settings
from app.semantic.loader import load_catalog

ANOMALY_DAYS = 14
ZONE_WEIGHT = {"North": 0.35, "South": 0.25, "East": 0.20, "West": 0.20}
MARKETPLACES = [("Acme Mall", 0.40), ("Acme Express", 0.30), ("Acme Wholesale", 0.30)]
BUSINESS_UNITS = [("Electronics", 0.30), ("Fashion", 0.25), ("Home", 0.20), ("Grocery", 0.15), ("Beauty", 0.10)]
UNIT_PRICE = {"Electronics": 60, "Fashion": 25, "Home": 35, "Grocery": 8, "Beauty": 15}
VISIT_CVR = {"Acme Mall": 0.030, "Acme Express": 0.040, "Acme Wholesale": 0.020}
BU_VISIT_CVR = 0.06
BASE_CANCEL, ANOMALY_CANCEL = 0.06, 0.60
TRACKING_LOSS_FACTOR = 0.45
MIX_OVERRIDE = 0.45


def _case(col: str, weighted: list[tuple[str, float]]) -> str:
    acc, parts = 0.0, []
    for value, w in weighted[:-1]:
        acc += w
        parts.append(f"WHEN {col} < {acc:.6f} THEN '{value}'")
    return f"CASE {' '.join(parts)} ELSE '{weighted[-1][0]}' END"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=20_000_000, help="orders to generate")
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--end", default="2026-09-30", help="last date (the dataset anchor)")
    args = ap.parse_args()

    settings = get_settings()
    hierarchy = load_catalog(settings.semantic_dir).dimensions["city"].hierarchy
    per_zone: dict[str, list[str]] = {}
    for city, anc in hierarchy.items():
        per_zone.setdefault(anc["zone"], []).append(city)
    city_weights = [(c, ZONE_WEIGHT[z] / len(cs)) for z, cs in per_zone.items() for c in cs]

    path = Path(settings.duckdb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    con = duckdb.connect(str(path))
    con.execute("SELECT setseed(0.42)")
    con.execute("CREATE TABLE dim_geo (city VARCHAR, state VARCHAR, region VARCHAR, zone VARCHAR)")
    con.executemany("INSERT INTO dim_geo VALUES (?,?,?,?)", [(c, a["state"], a["region"], a["zone"]) for c, a in hierarchy.items()])

    end, win = f"DATE '{args.end}'", f"{ANOMALY_DAYS}"
    recent = f"order_date > {end} - {win}"
    price_case = "CASE business_unit " + " ".join(f"WHEN '{b}' THEN {p}" for b, p in UNIT_PRICE.items()) + " END"
    con.execute(f"""
    CREATE TABLE fact_sales AS
    WITH base AS (
      SELECT i AS order_id, {end} - CAST(floor(random() * {args.days}) AS INTEGER) AS order_date,
             random() AS r_city, random() AS r_mkt, random() AS r_bu, random() AS r_price, random() AS r_units,
             random() AS r_cancel, random() AS r_mix
      FROM range({args.rows}) t(i)
    ), located AS (
      SELECT b.*, g.state, g.region, g.zone, g.city
      FROM (SELECT *, {_case('r_city', city_weights)} AS city FROM base) b JOIN dim_geo g USING (city)
    ), shaped AS (
      SELECT *, {_case('r_mkt', MARKETPLACES)} AS marketplace, {_case('r_bu', BUSINESS_UNITS)} AS bu0 FROM located
    ), mixed AS (
      SELECT *, CASE WHEN marketplace = 'Acme Wholesale' AND zone = 'North' AND {recent} AND r_mix < {MIX_OVERRIDE}
                     THEN 'Grocery' ELSE bu0 END AS business_unit FROM shaped
    ), priced AS (
      SELECT *, 1 + CAST(floor(r_units * r_units * 4) AS INTEGER) AS units,
             r_cancel < CASE WHEN marketplace = 'Acme Express' AND zone = 'South' AND {recent}
                             THEN {ANOMALY_CANCEL} ELSE {BASE_CANCEL} END AS cancelled
      FROM mixed
    ), valued AS (
      SELECT *, ROUND(units * {price_case} * (0.6 + r_price), 2) AS gmv FROM priced
    )
    SELECT order_id, order_date, marketplace, business_unit, zone, region, state, city,
           1 AS orders, units AS gross_units, gmv AS gross_gmv,
           CASE WHEN cancelled THEN 0 ELSE units END AS net_units,
           CASE WHEN cancelled THEN 0 ELSE gmv END AS net_gmv
    FROM valued
    """)

    con.execute("""
    CREATE TABLE agg_sales_daily AS
    SELECT order_date, marketplace, business_unit, zone, region, state,
           SUM(orders) AS orders, SUM(gross_units) AS gross_units, SUM(net_units) AS net_units,
           SUM(gross_gmv) AS gross_gmv, SUM(net_gmv) AS net_gmv
    FROM fact_sales GROUP BY ALL
    """)

    visit_cvr = "CASE marketplace " + " ".join(f"WHEN '{m}' THEN {v}" for m, v in VISIT_CVR.items()) + " END"
    tracking_loss = f"marketplace = 'Acme Mall' AND zone = 'East' AND visit_date > {end} - {win}"
    con.execute(f"""
    CREATE TABLE agg_traffic_city_daily AS
    WITH o AS (SELECT order_date AS visit_date, marketplace, zone, region, state, city, SUM(orders) AS orders
               FROM fact_sales GROUP BY ALL)
    SELECT visit_date, marketplace, zone, region, state, city,
           CAST(ROUND(orders / ({visit_cvr}) * (0.95 + 0.10 * random())
                      * CASE WHEN {tracking_loss} THEN {TRACKING_LOSS_FACTOR} ELSE 1 END) AS BIGINT) AS visits,
           orders
    FROM o
    """)
    con.execute("""
    CREATE TABLE agg_traffic_state_daily AS
    SELECT visit_date, marketplace, zone, region, state, SUM(visits) AS visits, SUM(orders) AS orders
    FROM agg_traffic_city_daily GROUP BY ALL
    """)
    con.execute(f"""
    CREATE TABLE agg_bu_traffic_daily AS
    WITH o AS (SELECT order_date AS visit_date, marketplace, business_unit, zone, region, state, SUM(orders) AS orders
               FROM fact_sales GROUP BY ALL)
    SELECT visit_date, marketplace, business_unit, zone, region, state,
           CAST(ROUND(orders / {BU_VISIT_CVR} * (0.95 + 0.10 * random())
                      * CASE WHEN {tracking_loss} THEN {TRACKING_LOSS_FACTOR} ELSE 1 END) AS BIGINT) AS bu_visits,
           orders
    FROM o
    """)

    for t in ("fact_sales", "agg_sales_daily", "agg_traffic_city_daily", "agg_traffic_state_daily", "agg_bu_traffic_daily"):
        print(f"{t:28s}{con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>12,} rows")
    con.close()


if __name__ == "__main__":
    main()
