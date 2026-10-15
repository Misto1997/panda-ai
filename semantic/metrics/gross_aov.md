---
kind: metric
id: gross_aov
title: Gross AOV
aliases:
- average order value
- AOV
- basket size
- order value
description: Gross GMV per order.
table: sales
numerator: SUM(gross_gmv)
denominator: SUM(orders)
unit: currency
format: currency
direction: up_is_good
dimensions:
- marketplace
- business_unit
- zone
- region
- state
- city
time_grains:
- day
- week
- month
---
Ratio of sums, before cancellations.
