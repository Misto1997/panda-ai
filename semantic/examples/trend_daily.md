---
kind: example
id: trend_daily
question: "Daily net GMV trend for the last 14 days"
tags: [trend, daily, time series]
sql: |
  SELECT DATE_TRUNC('day', order_date) AS date, SUM(net_gmv) AS net_gmv
  FROM sales
  WHERE order_date >= DATE '2026-09-17' AND order_date < DATE '2026-10-01'
  GROUP BY 1
  ORDER BY date
---
