---
kind: metric
id: net_realization_rate
title: Net-to-Gross Ratio
aliases:
- net to gross
- realization rate
- fulfilment rate
- net gross ratio
description: Net GMV divided by gross GMV. Falls when cancellations rise.
table: sales
numerator: SUM(net_gmv)
denominator: SUM(gross_gmv)
unit: percent
format: percent
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
1 minus the cancellation rate.
