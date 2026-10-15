---
kind: metric
id: visits
title: Visits
aliases:
- site visits
- traffic
- sessions
- footfall
description: Number of visits to the marketplaces. Not split by business unit.
table: traffic
expr: SUM(visits)
unit: number
format: number
direction: up_is_good
dimensions:
- marketplace
- zone
- region
- state
- city
time_grains:
- day
- week
- month
---
Top of the funnel.
