---
kind: example
id: follow_up_regrain
question: "Follow-up. Previous question: orders by zone last 14 days. Now: show it as a weekly trend"
tags: [follow-up, trend, change grain]
sql: |
  SELECT DATE_TRUNC('week', order_date) AS date, zone, SUM(orders) AS orders
  FROM sales
  WHERE order_date >= DATE '2026-09-17' AND order_date < DATE '2026-10-01'
  GROUP BY 1, 2
  ORDER BY date, zone
---
