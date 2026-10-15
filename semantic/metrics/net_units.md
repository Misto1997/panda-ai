---
kind: metric
id: net_units
title: Net Units
aliases:
- units sold
- items sold
- net quantity
- units
description: Units that were fulfilled.
table: sales
expr: SUM(net_units)
unit: number
format: number
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
Gross units minus cancelled units.
