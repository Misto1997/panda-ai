---
kind: example
id: breakdown_two_dimensions
question: "Orders by marketplace and business unit over the last 14 days"
tags: [breakdown, two dimensions, orders]
sql: |
  SELECT marketplace, business_unit, SUM(orders) AS orders
  FROM sales
  WHERE order_date >= DATE '2026-09-17' AND order_date < DATE '2026-10-01'
  GROUP BY marketplace, business_unit
  ORDER BY orders DESC
---
