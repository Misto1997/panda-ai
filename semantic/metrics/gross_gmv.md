---
kind: metric
id: gross_gmv
title: Gross GMV
aliases:
- gross merchandise value
- gross sales
- gross revenue
- GMV before cancellations
description: Value of all orders placed, before cancellations.
table: sales
expr: SUM(gross_gmv)
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
Sum of order value at order time, including orders later cancelled.
