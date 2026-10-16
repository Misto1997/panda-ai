---
kind: example
id: filter_exclusion
question: "ASP by business unit excluding Grocery for the last 30 days"
tags: [filter, exclude, ratio, asp]
sql: |
  SELECT business_unit, SUM(net_gmv) / NULLIF(SUM(net_units), 0) AS asp
  FROM sales
  WHERE order_date >= DATE '2026-09-01' AND order_date < DATE '2026-10-01'
    AND business_unit NOT IN ('Grocery')
  GROUP BY business_unit
  ORDER BY asp DESC
---
