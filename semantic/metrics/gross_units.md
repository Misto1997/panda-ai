---
kind: metric
id: gross_units
title: Gross Units
aliases:
- units ordered
- items ordered
- gross quantity
description: Units across all orders placed, before cancellations.
table: sales
expr: SUM(gross_units)
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
Sum of item quantities at order time.
