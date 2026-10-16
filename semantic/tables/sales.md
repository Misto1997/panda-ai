---
kind: table
id: sales
title: Sales
anchor: true
description: Order-level sales facts. Served from the daily rollup (state grain) when every requested dimension exists there; city-level questions fall back to the raw fact table.
raw: fact_sales
rollup: agg_sales_daily
time_column: order_date
measures: [orders, gross_units, net_units, gross_gmv, net_gmv]
rollup_dimensions:
- marketplace
- business_unit
- zone
- region
- state
---
Raw table: one row per order. Rollup: daily, state grain.
