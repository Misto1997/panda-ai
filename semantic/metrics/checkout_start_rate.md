---
kind: metric
id: checkout_start_rate
title: Checkout Start Rate
aliases: [cart to checkout rate, checkout rate]
description: Checkout starts divided by sessions.
table: traffic
numerator: SUM(checkout_starts)
denominator: SUM(sessions)
unit: ratio
format: percent
direction: up_is_good
dimensions: [region, channel]
time_grains: [day, week, month]
---
Middle of the funnel: sessions to checkout starts.
