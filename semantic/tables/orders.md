---
kind: table
id: orders
title: Orders
description: Order-level commerce facts for Acme Retail. Queries are served from the daily rollup when every requested dimension is available in it, otherwise from the raw fact table.
raw: fact_orders
rollup: agg_orders_daily
time_column: order_date
rollup_dimensions: [region, channel, category, customer_segment]
---
Raw table holds one row per order (very large). The rollup is pre-aggregated by day and the four dimensions and answers most questions in milliseconds.
