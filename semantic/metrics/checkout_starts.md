---
kind: metric
id: checkout_starts
title: Checkout Starts
aliases: [checkouts started, cart to checkout]
description: Sessions that reached checkout.
table: traffic
expr: SUM(checkout_starts)
unit: count
format: number
direction: up_is_good
dimensions: [region, channel]
time_grains: [day, week, month]
---
Middle of the funnel.
