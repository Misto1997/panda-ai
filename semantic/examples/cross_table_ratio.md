---
kind: example
id: cross_table_ratio
question: "Net GMV per visit by marketplace over the last 14 days"
tags: [multi table, derived ratio, visits, net gmv]
sql: |
  WITH s AS (
    SELECT marketplace, SUM(net_gmv) AS net_gmv
    FROM sales
    WHERE order_date >= DATE '2026-09-17' AND order_date < DATE '2026-10-01'
    GROUP BY marketplace
  ), t AS (
    SELECT marketplace, SUM(visits) AS visits
    FROM traffic
    WHERE visit_date >= DATE '2026-09-17' AND visit_date < DATE '2026-10-01'
    GROUP BY marketplace
  )
  SELECT s.marketplace, s.net_gmv / NULLIF(t.visits, 0) AS net_gmv_per_visit
  FROM s
  JOIN t ON s.marketplace = t.marketplace
  ORDER BY net_gmv_per_visit DESC
---
