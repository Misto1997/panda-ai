---
kind: example
id: breakdown_zone
question: "Net GMV by zone for the last 7 days"
tags: [breakdown, zone, net gmv]
sql: |
  SELECT zone, SUM(net_gmv) AS net_gmv
  FROM sales
  WHERE order_date >= DATE '2026-09-24' AND order_date < DATE '2026-10-01'
  GROUP BY zone
  ORDER BY net_gmv DESC
---
