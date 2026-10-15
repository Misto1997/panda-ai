---
kind: metric
id: discount_rate
title: Discount Rate
aliases: [discounting, discount depth]
description: Discount given as a share of GMV.
table: orders
numerator: SUM(discount)
denominator: SUM(gmv)
unit: ratio
format: percent
direction: neutral
dimensions: [region, channel, category, customer_segment]
time_grains: [day, week, month]
---
Discount amount / GMV.
