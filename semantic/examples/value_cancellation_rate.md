---
kind: example
id: value_cancellation_rate
question: "What is the cancellation rate for the last 30 days?"
tags: [value, ratio, cancellation]
sql: |
  SELECT (SUM(gross_gmv) - SUM(net_gmv)) / NULLIF(SUM(gross_gmv), 0) AS cancellation_rate
  FROM sales
  WHERE order_date >= DATE '2026-09-01' AND order_date < DATE '2026-10-01'
---
