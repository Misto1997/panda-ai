---
kind: example
id: topn_cities_city_level
question: "Top 5 cities by orders in the last 7 days"
tags: [top n, city, city level, raw]
sql: |
  SELECT city, SUM(orders) AS orders
  FROM sales
  WHERE order_date >= DATE '2026-09-24' AND order_date < DATE '2026-10-01'
  GROUP BY city
  ORDER BY orders DESC
  LIMIT 5
---
