---
kind: metric
id: net_gmv
title: Net GMV
aliases:
- net merchandise value
- net sales
- net revenue
- GMV
- revenue
- sales
description: Value of orders that were fulfilled (gross GMV minus cancellations).
table: sales
expr: SUM(net_gmv)
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
Primary top-line metric. Net GMV = Visits x Conversion x Gross AOV x Net-to-Gross ratio.
