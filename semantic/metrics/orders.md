---
kind: metric
id: orders
title: Orders
aliases:
- order count
- number of orders
- order volume
- gross orders
description: Number of orders placed, including later cancellations.
table: sales
expr: SUM(orders)
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
One row per order in the raw table.
