---
kind: metric
id: checkout_completion_rate
title: Checkout Completion Rate
aliases: [checkout success rate, payment success]
description: Orders divided by checkout starts. A drop usually signals payment or checkout friction.
table: traffic
numerator: SUM(orders)
denominator: SUM(checkout_starts)
unit: ratio
format: percent
direction: up_is_good
dimensions: [region, channel]
time_grains: [day, week, month]
---
Bottom of the funnel.
