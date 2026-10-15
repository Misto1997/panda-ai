---
kind: metric
id: bu_conversion_rate
title: BU Conversion Rate
aliases:
- business unit conversion
- vertical conversion
description: Orders divided by BU visits.
table: bu_traffic
numerator: SUM(orders)
denominator: SUM(bu_visits)
unit: percent
format: percent
direction: up_is_good
dimensions:
- marketplace
- business_unit
- zone
- region
- state
time_grains:
- day
- week
- month
---
Order conversion measured against business-unit visits.
