---
kind: metric
id: orders
title: Orders
aliases: [order count, number of orders, order volume]
description: Number of orders placed.
table: orders
expr: SUM(orders)
unit: count
format: number
direction: up_is_good
dimensions: [region, channel, category, customer_segment]
time_grains: [day, week, month]
---
Counts every placed order, including those later returned.
