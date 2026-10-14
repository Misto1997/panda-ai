"""Generate deterministic synthetic Acme Retail data into DuckDB.

Planted anomaly: in the last 14 days, Android orders in the West region lose ~65% of
checkout completions (sessions and checkout starts are unchanged). RCA should find it.

Usage: python scripts/generate_data.py [--rows 20000000] [--days 120]
"""
import argparse
from pathlib import Path

import duckdb

from app.config import get_settings

ANOMALY_DAYS = 14
ANOMALY_DROP = 0.65


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=20_000_000, help="raw order rows before anomaly removal")
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--end", default="2026-09-30", help="last date (anchor)")
    args = ap.parse_args()

    path = Path(get_settings().duckdb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    con = duckdb.connect(str(path))
    con.execute("SELECT setseed(0.42)")

    con.execute(f"""
    CREATE TABLE fact_orders AS
    WITH base AS (
      SELECT
        i AS order_id,
        DATE '{args.end}' - CAST(floor(random() * {args.days}) AS INTEGER) AS order_date,
        random() AS r_region, random() AS r_channel, random() AS r_cat, random() AS r_seg,
        random() AS r_price, random() AS r_disc, random() AS r_ret, random() AS r_units, random() AS r_drop
      FROM range({args.rows}) t(i)
    ), shaped AS (
      SELECT order_id, order_date,
        CASE WHEN r_region < 0.30 THEN 'North' WHEN r_region < 0.55 THEN 'South' WHEN r_region < 0.75 THEN 'East' ELSE 'West' END AS region,
        CASE WHEN r_channel < 0.40 THEN 'android' WHEN r_channel < 0.70 THEN 'ios' ELSE 'web' END AS channel,
        CASE WHEN r_cat < 0.30 THEN 'Electronics' WHEN r_cat < 0.55 THEN 'Fashion' WHEN r_cat < 0.75 THEN 'Home' WHEN r_cat < 0.90 THEN 'Grocery' ELSE 'Beauty' END AS category,
        CASE WHEN r_seg < 0.35 THEN 'new' WHEN r_seg < 0.80 THEN 'returning' ELSE 'loyalty' END AS customer_segment,
        1 + CAST(floor(r_units * r_units * 4) AS INTEGER) AS units,
        r_price, r_disc, r_ret, r_drop
      FROM base
    )
    SELECT
      order_id, order_date, region, channel, category, customer_segment,
      1 AS orders,
      units,
      ROUND(units * (CASE category WHEN 'Electronics' THEN 60 WHEN 'Fashion' THEN 25 WHEN 'Home' THEN 35 WHEN 'Grocery' THEN 8 ELSE 15 END) * (0.6 + r_price), 2) AS gmv,
      ROUND(units * (CASE category WHEN 'Electronics' THEN 60 WHEN 'Fashion' THEN 25 WHEN 'Home' THEN 35 WHEN 'Grocery' THEN 8 ELSE 15 END) * (0.6 + r_price) * (CASE WHEN r_disc < 0.5 THEN 0 ELSE 0.05 + 0.2 * r_disc END), 2) AS discount,
      CASE WHEN r_ret < (CASE category WHEN 'Fashion' THEN 0.18 WHEN 'Electronics' THEN 0.07 ELSE 0.04 END) THEN 1 ELSE 0 END AS returned_orders
    FROM shaped
    WHERE NOT (region = 'West' AND channel = 'android'
               AND order_date > DATE '{args.end}' - {ANOMALY_DAYS} AND r_drop < {ANOMALY_DROP})
    """)

    con.execute("""
    CREATE TABLE agg_orders_daily AS
    SELECT order_date, region, channel, category, customer_segment,
           SUM(orders) AS orders, SUM(units) AS units, SUM(gmv) AS gmv,
           SUM(discount) AS discount, SUM(returned_orders) AS returned_orders
    FROM fact_orders GROUP BY ALL
    """)

    # Sessions and checkout starts are generated independently of orders; they do not
    # reflect the anomaly, so conversion drops only because checkout completion drops.
    con.execute(f"""
    CREATE TABLE agg_traffic_daily AS
    WITH o AS (
      SELECT order_date AS event_date, region, channel, SUM(orders) AS orders FROM agg_orders_daily GROUP BY ALL
    ), exp AS (
      SELECT event_date, region, channel,
             orders,
             -- expected orders if no anomaly: add back the planted drop
             CASE WHEN region = 'West' AND channel = 'android' AND event_date > DATE '{args.end}' - {ANOMALY_DAYS}
                  THEN orders / (1 - {ANOMALY_DROP}) ELSE orders END AS expected_orders
      FROM o
    )
    SELECT event_date, region, channel,
           CAST(ROUND(expected_orders / (CASE channel WHEN 'web' THEN 0.025 WHEN 'ios' THEN 0.035 ELSE 0.03 END)
                      * (0.97 + 0.06 * random())) AS BIGINT) AS sessions,
           0 AS checkout_starts,
           orders
    FROM exp
    """)
    con.execute("UPDATE agg_traffic_daily SET checkout_starts = CAST(ROUND(sessions * 0.16 * (0.97 + 0.06 * random())) AS BIGINT)")

    for t in ("fact_orders", "agg_orders_daily", "agg_traffic_daily"):
        print(t, con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], "rows")
    con.close()


if __name__ == "__main__":
    main()
