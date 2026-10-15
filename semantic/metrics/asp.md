---
kind: metric
id: asp
title: Average Selling Price
aliases:
- ASP
- average price
- price per unit
description: Net GMV per net unit.
table: sales
numerator: SUM(net_gmv)
denominator: SUM(net_units)
unit: currency
format: currency
direction: neutral
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
Ratio of sums. Sensitive to business-unit mix.
