---
kind: table
id: bu_traffic
title: Business unit traffic
description: Daily visits to each business unit's pages. A visit touching several business units counts once per unit, so BU visits do not sum to total visits.
raw: agg_bu_traffic_daily
rollup: agg_bu_traffic_daily
time_column: visit_date
measures: [bu_visits, orders]
rollup_dimensions:
- marketplace
- business_unit
- zone
- region
- state
---
Not additive across business units.
