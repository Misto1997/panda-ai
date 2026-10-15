---
kind: dimension
id: date
title: Date
aliases:
- day
- time
- period
description: Calendar date of the order or visit. Supports day, week and month grains.
column: date
tables:
- sales
- traffic
- bu_traffic
values: []
---
Time dimension. Relative periods resolve from the latest loaded date.
