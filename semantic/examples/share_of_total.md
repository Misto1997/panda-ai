---
kind: example
id: share_of_total
question: "Share of net GMV by business unit for the last 30 days"
tags: [share, mix, window, business unit]
sql: |
  SELECT business_unit,
         SUM(net_gmv) AS net_gmv,
         SUM(net_gmv) / NULLIF(SUM(SUM(net_gmv)) OVER (), 0) AS share_of_net_gmv
  FROM sales
  WHERE order_date >= DATE '2026-09-01' AND order_date < DATE '2026-10-01'
  GROUP BY business_unit
  ORDER BY net_gmv DESC
---
