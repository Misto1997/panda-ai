---
kind: metric
id: aov
title: Average Order Value
aliases: [AOV, basket size, average basket]
description: Average GMV per order.
table: orders
numerator: SUM(gmv)
denominator: SUM(orders)
unit: currency
format: currency
direction: up_is_good
dimensions: [region, channel, category, customer_segment]
time_grains: [day, week, month]
---
Ratio metric: GMV / Orders. Compute from sums, never average daily AOV.
