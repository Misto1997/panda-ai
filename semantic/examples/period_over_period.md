---
kind: example
id: period_over_period
question: "Compare net GMV by zone for the last 7 days with the previous 7 days, with percent change"
tags: [period over period, comparison, growth, change]
sql: |
  WITH cur AS (
    SELECT zone, SUM(net_gmv) AS net_gmv
    FROM sales
    WHERE order_date >= DATE '2026-09-24' AND order_date < DATE '2026-10-01'
    GROUP BY zone
  ), prev AS (
    SELECT zone, SUM(net_gmv) AS net_gmv
    FROM sales
    WHERE order_date >= DATE '2026-09-17' AND order_date < DATE '2026-09-24'
    GROUP BY zone
  )
  SELECT cur.zone, cur.net_gmv AS net_gmv, prev.net_gmv AS previous_net_gmv,
         (cur.net_gmv - prev.net_gmv) / NULLIF(prev.net_gmv, 0) AS pct_change
  FROM cur
  JOIN prev ON cur.zone = prev.zone
  ORDER BY pct_change
---
