---
kind: example
id: trend_weekly_ratio
question: "Weekly conversion rate for the last 90 days"
tags: [trend, weekly, ratio, conversion]
sql: |
  SELECT DATE_TRUNC('week', visit_date) AS date, SUM(orders) / NULLIF(SUM(visits), 0) AS conversion_rate
  FROM traffic
  WHERE visit_date >= DATE '2026-07-03' AND visit_date < DATE '2026-10-01'
  GROUP BY 1
  ORDER BY date
---
