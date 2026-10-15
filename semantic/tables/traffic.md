---
kind: table
id: traffic
title: Traffic
description: Daily site visits and orders per marketplace and location. Visits are not attributed to a business unit.
raw: agg_traffic_city_daily
rollup: agg_traffic_state_daily
time_column: visit_date
rollup_dimensions:
- marketplace
- zone
- region
- state
---
Raw: city grain. Rollup: state grain.
