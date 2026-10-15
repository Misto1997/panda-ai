---
kind: metric
id: cancellation_rate
title: Cancellation Rate
aliases:
- cancellations
- cancelled share
- GMV leakage
description: Share of gross GMV lost to cancellations.
table: sales
numerator: SUM(gross_gmv) - SUM(net_gmv)
denominator: SUM(gross_gmv)
unit: percent
format: percent
direction: down_is_good
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
(Gross GMV - Net GMV) / Gross GMV.
