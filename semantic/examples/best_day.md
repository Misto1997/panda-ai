---
kind: example
id: best_day
question: "Which day had the highest net GMV in the last 30 days?"
tags: [top n, day, peak, single row]
sql: |
  SELECT DATE_TRUNC('day', order_date) AS date, SUM(net_gmv) AS net_gmv
  FROM sales
  WHERE order_date >= DATE '2026-09-01' AND order_date < DATE '2026-10-01'
  GROUP BY 1
  ORDER BY net_gmv DESC
  LIMIT 1
---
