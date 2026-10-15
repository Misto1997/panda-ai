---
kind: metric
id: return_rate
title: Return Rate
aliases: [returns, returned orders share]
description: Share of orders that were returned.
table: orders
numerator: SUM(returned_orders)
denominator: SUM(orders)
unit: ratio
format: percent
direction: down_is_good
dimensions: [region, channel, category, customer_segment]
time_grains: [day, week, month]
---
Returned orders / orders.
