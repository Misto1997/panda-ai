---
kind: example
id: bu_conversion
question: "Business unit conversion rate by business unit over the last 14 days"
tags: [ratio, bu traffic, conversion]
sql: |
  SELECT business_unit, SUM(orders) / NULLIF(SUM(bu_visits), 0) AS bu_conversion_rate
  FROM bu_traffic
  WHERE visit_date >= DATE '2026-09-17' AND visit_date < DATE '2026-10-01'
  GROUP BY business_unit
  ORDER BY bu_conversion_rate DESC
---
