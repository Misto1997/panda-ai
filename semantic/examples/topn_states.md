---
kind: example
id: topn_states
question: "Top 5 states by net GMV last month"
tags: [top n, state, last month]
sql: |
  SELECT state, SUM(net_gmv) AS net_gmv
  FROM sales
  WHERE order_date >= DATE '2026-09-01' AND order_date < DATE '2026-10-01'
  GROUP BY state
  ORDER BY net_gmv DESC
  LIMIT 5
---
