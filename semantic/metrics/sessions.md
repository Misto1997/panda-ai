---
kind: metric
id: sessions
title: Sessions
aliases: [visits, traffic]
description: Number of storefront sessions.
table: traffic
expr: SUM(sessions)
unit: count
format: number
direction: up_is_good
dimensions: [region, channel]
time_grains: [day, week, month]
---
Top of the funnel.
