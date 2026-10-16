---
kind: example
id: filter_two_dimensions
question: "Net GMV for Acme Express in the South zone over the last 7 days"
tags: [filter, marketplace, zone, value]
sql: |
  SELECT SUM(net_gmv) AS net_gmv
  FROM sales
  WHERE order_date >= DATE '2026-09-24' AND order_date < DATE '2026-10-01'
    AND marketplace = 'Acme Express' AND zone = 'South'
---
