---
kind: example
id: value_net_gmv_yesterday
question: "What was net GMV yesterday?"
tags: [value, single period, yesterday]
sql: |
  SELECT SUM(net_gmv) AS net_gmv
  FROM sales
  WHERE order_date >= DATE '2026-09-30' AND order_date < DATE '2026-10-01'
---
