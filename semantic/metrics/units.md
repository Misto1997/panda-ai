---
kind: metric
id: units
title: Units Sold
aliases: [items sold, quantity]
description: Number of items sold.
table: orders
expr: SUM(units)
unit: count
format: number
direction: up_is_good
dimensions: [region, channel, category, customer_segment]
time_grains: [day, week, month]
---
Sum of item quantities across orders.
