---
kind: example
id: multi_table_join
question: "Net GMV and visits by marketplace for the last 7 days"
tags: [multi table, join, net gmv, visits]
sql: |
  WITH s AS (
    SELECT marketplace, SUM(net_gmv) AS net_gmv
    FROM sales
    WHERE order_date >= DATE '2026-09-24' AND order_date < DATE '2026-10-01'
    GROUP BY marketplace
  ), t AS (
    SELECT marketplace, SUM(visits) AS visits
    FROM traffic
    WHERE visit_date >= DATE '2026-09-24' AND visit_date < DATE '2026-10-01'
    GROUP BY marketplace
  )
  SELECT s.marketplace, s.net_gmv AS net_gmv, t.visits AS visits
  FROM s
  JOIN t ON s.marketplace = t.marketplace
  ORDER BY net_gmv DESC
---
