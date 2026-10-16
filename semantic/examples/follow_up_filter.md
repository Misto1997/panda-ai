---
kind: example
id: follow_up_filter
question: "Follow-up. Previous question: net GMV by marketplace last 7 days. Now: only the West zone"
tags: [follow-up, filter, refine previous sql]
sql: |
  SELECT marketplace, SUM(net_gmv) AS net_gmv
  FROM sales
  WHERE order_date >= DATE '2026-09-24' AND order_date < DATE '2026-10-01'
    AND zone = 'West'
  GROUP BY marketplace
  ORDER BY net_gmv DESC
---
