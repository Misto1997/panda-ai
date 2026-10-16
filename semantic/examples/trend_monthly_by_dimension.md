---
kind: example
id: trend_monthly_by_dimension
question: "Monthly orders by marketplace for the last 90 days"
tags: [trend, monthly, breakdown]
sql: |
  SELECT DATE_TRUNC('month', order_date) AS date, marketplace, SUM(orders) AS orders
  FROM sales
  WHERE order_date >= DATE '2026-07-03' AND order_date < DATE '2026-10-01'
  GROUP BY 1, 2
  ORDER BY date, marketplace
---
