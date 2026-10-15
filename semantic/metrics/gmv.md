---
kind: metric
id: gmv
title: Gross Merchandise Value
aliases: [revenue, sales, gross sales, GMV]
description: Total value of orders before returns and discounts are netted.
table: orders
expr: SUM(gmv)
unit: currency
format: currency
direction: up_is_good
dimensions: [region, channel, category, customer_segment]
time_grains: [day, week, month]
---
Primary top-line metric. GMV = Sessions x Conversion Rate x AOV.
