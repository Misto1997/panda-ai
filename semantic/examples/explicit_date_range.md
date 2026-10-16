---
kind: example
id: explicit_date_range
question: "Orders by region between 2026-09-01 and 2026-09-15"
tags: [explicit dates, range, region]
sql: |
  SELECT region, SUM(orders) AS orders
  FROM sales
  WHERE order_date >= DATE '2026-09-01' AND order_date < DATE '2026-09-16'
  GROUP BY region
  ORDER BY orders DESC
---
